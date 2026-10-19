"""Small, physics-validated waypoint search for platform characters.

Nodes are safe standing positions above solid tiles. Edges are adjacent
walking steps, or landings found by simulating the character's actual jump or
walk-off trajectory through the world's swept tile collisions.
"""
from dataclasses import dataclass
from enum import Enum
import heapq
import itertools
import math
from types import SimpleNamespace

from src.combat import line_clear
from src.physics import integrate_character, overlaps_solid


@dataclass(frozen=True)
class NavStep:
    x: float
    y: float
    action: str = "walk"  # walk, jump, or drop
    takeoff_x: float | None = None
    takeoff_y: float | None = None
    edge_id: tuple | None = None


@dataclass(frozen=True)
class NavEdge:
    destination: tuple[int, int]
    action: str
    cost: float
    takeoff: tuple[float, float]


@dataclass
class PlatformGraph:
    bounds: tuple[int, int, int, int]
    nodes: frozenset
    platforms: tuple[tuple[tuple[int, int], ...], ...]
    platform_by_node: dict
    edges: dict
    platform_edges: dict


class PathStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class PathResult:
    status: PathStatus
    steps: tuple[NavStep, ...] = ()
    endpoint: tuple[float, float] | None = None
    expansions: int = 0

    @property
    def complete(self):
        return self.status == PathStatus.COMPLETE


@dataclass(frozen=True)
class NavigationSettings:
    max_expansions: int = 240
    max_area_width: int = 32
    max_jump_ticks: int = 100
    max_drop_tiles: float = 6
    jump_failure_cooldown_ms: float = 1800


def _lava_overlap(world, x, y, physics):
    size = physics.tile_size
    return any(world.is_lava(c, r)
               for r in range(math.floor(y/size), math.ceil((y+physics.height)/size))
               for c in range(math.floor(x/size), math.ceil((x+physics.width)/size)))


class PlatformNavigator:
    """Bounded A* over physically valid platform transitions."""

    def __init__(self, physics, speed, settings=None):
        self.physics = physics
        self.speed = float(speed)
        self.settings = settings or NavigationSettings()
        self._failed_edges = {}
        self._world_graph_cache = None

    def update(self, dt):
        """Age temporary transition penalties without affecting world data."""
        for edge_id in list(self._failed_edges):
            remaining = self._failed_edges[edge_id]-dt
            if remaining <= 0:
                del self._failed_edges[edge_id]
            else:
                self._failed_edges[edge_id] = remaining

    def fail_transition(self, edge_id):
        if edge_id is not None:
            self._failed_edges[edge_id] = self.settings.jump_failure_cooldown_ms

    def graph_for_debug(self):
        return self._world_graph_cache

    @property
    def failed_transitions(self):
        return self._failed_edges

    def _position(self, node):
        col, foot_row = node
        p = self.physics
        return (col*p.tile_size+(p.tile_size-p.width)/2,
                foot_row*p.tile_size-p.height)

    def _node_at(self, world, x, y):
        p = self.physics
        col = math.floor((x+p.width/2)/p.tile_size)
        foot = round((y+p.height)/p.tile_size)
        node = (col, foot)
        nx, ny = self._position(node)
        if abs(nx-x) > p.tile_size*.55 or abs(ny-y) > 3:
            return None
        if not world.is_solid(col, foot) or world.is_lava(col, foot):
            return None
        if overlaps_solid(world, nx, ny, p.width, p.height, p.tile_size):
            return None
        if _lava_overlap(world, nx, ny, p):
            return None
        return node

    def _landing(self, world, node, direction, jump):
        p = self.physics
        x, y = self._position(node)
        probe = SimpleNamespace(world=world, x=x, y=y,
            vx=direction*self.speed,
            vy=p.jump_velocity if jump else 0.0,
            on_ground=not jump)
        for tick in range(self.settings.max_jump_ticks):
            # The AI holds the direction throughout the arc; reapply it after
            # a swept collision just as the real update loop does next tick.
            probe.vx = direction*self.speed
            integrate_character(probe, p.step_ms, p)
            if _lava_overlap(world, probe.x, probe.y, p):
                return None
            if probe.y > y+self.settings.max_drop_tiles*p.tile_size:
                return None
            if probe.on_ground and tick >= 2:
                landing = self._node_at(world, probe.x, probe.y)
                if landing is not None and landing != node:
                    return landing
        return None

    def safe_drop_landing(self, world, node, direction):
        """Return a collision- and lava-validated lower landing, if reachable."""
        return self._landing(world, node, direction, False)

    def _bounds(self, start, goal, world):
        p = self.physics
        start_c = math.floor((start[0]+p.width/2)/p.tile_size)
        goal_c = math.floor(goal[0]/p.tile_size)
        half = self.settings.max_area_width//2
        left = max(1, min(start_c, goal_c)-4)
        right = min(round(p.world_width/p.tile_size)-2, max(start_c, goal_c)+4)
        if right-left > self.settings.max_area_width:
            midpoint = (start_c+goal_c)//2
            left = max(1, midpoint-half)
            right = min(round(p.world_width/p.tile_size)-2,
                        left+self.settings.max_area_width)
            left = max(1, right-self.settings.max_area_width)
        start_row = round((start[1]+p.height)/p.tile_size)
        goal_row = round((goal[1]+p.height)/p.tile_size)
        top = max(1, min(start_row, goal_row)-5)
        bottom = min(len(world.tiles)-1,
                     math.ceil(max(start_row, goal_row)+self.settings.max_drop_tiles+3))
        return left, right, top, bottom

    def _region_signature(self, world, bounds):
        revision = getattr(world, "navigation_revision", 0)
        changes = getattr(world, "navigation_changes", None)
        if changes is None or not changes:
            return revision
        left, right, top, bottom = bounds
        local = tuple((rev, col, row) for rev, col, row in changes
                      if left-2 <= col <= right+2 and top-2 <= row <= bottom+2)
        # A missing part of the change log means this cache may predate edits.
        floor = getattr(world, "navigation_change_floor", 0)
        graph = self._world_graph_cache
        if graph and graph[0] == id(world) and graph[2] < floor:
            return revision
        return local

    def _build_graph(self, world, bounds):
        p = self.physics
        left, right, top, bottom = bounds
        nodes = set()
        for col in range(left, right+1):
            for foot in range(top, bottom+1):
                x, y = self._position((col, foot))
                if (world.is_solid(col, foot) and not world.is_lava(col, foot)
                        and not overlaps_solid(world, x, y, p.width, p.height, p.tile_size)
                        and not _lava_overlap(world, x, y, p)):
                    nodes.add((col, foot))

        # Group horizontal runs of supported, safe cells into platform regions.
        platforms = []
        platform_by_node = {}
        for node in sorted(nodes, key=lambda n: (n[1], n[0])):
            if node in platform_by_node:
                continue
            foot = node[1]
            run = [node]
            col = node[0]+1
            while (col, foot) in nodes:
                run.append((col, foot))
                col += 1
            index = len(platforms)
            group = tuple(run)
            platforms.append(group)
            for member in group:
                platform_by_node[member] = index

        edges = {node: [] for node in nodes}
        for node in nodes:
            col, foot = node
            x, y = self._position(node)
            risk = self._risk(world, node)
            for direction in (-1, 1):
                adjacent = (col+direction, foot)
                if adjacent in nodes:
                    edges[node].append(NavEdge(adjacent, "walk", 1.0+risk,
                                               (x, y)))
                for jumping in (True, False):
                    if not jumping and adjacent in nodes:
                        continue
                    landing = self._landing(world, node, direction, jumping)
                    if landing not in nodes:
                        continue
                    lx, ly = self._position(landing)
                    distance = abs(lx-x)/p.tile_size+abs(ly-y)/p.tile_size*.35
                    action = "jump" if jumping else "drop"
                    # Safe, shorter detours win; long/danger-adjacent drops and
                    # jumps cost more without becoming physically impossible.
                    edge_cost = max(1.0, distance) + self._risk(world, landing)
                    if action == "jump":
                        edge_cost += .15
                    else:
                        edge_cost += max(0.0, (ly-y)/p.tile_size)*.18
                    edges[node].append(NavEdge(landing, action, edge_cost, (x, y)))
        platform_edges = {index: [] for index in range(len(platforms))}
        for source, outgoing in edges.items():
            source_platform = platform_by_node[source]
            for edge in outgoing:
                destination_platform = platform_by_node[edge.destination]
                if destination_platform != source_platform:
                    platform_edges[source_platform].append((source, edge))
        return PlatformGraph(bounds, frozenset(nodes), tuple(platforms),
                             platform_by_node, edges, platform_edges)

    def _risk(self, world, node):
        col, foot = node
        # Keep one-tile clearance from lava pockets when alternatives exist.
        nearby = any(world.is_lava(c, r)
                     for c in range(col-1, col+2)
                     for r in range(foot-2, foot+1))
        return 1.25 if nearby else 0.0

    def _graph(self, world, bounds):
        signature = self._region_signature(world, bounds)
        key = (self.physics, self.speed, self.settings, bounds, signature)
        cache = getattr(world, "_platform_navigation_graph_cache", None)
        if cache is None:
            cache = {}
            world._platform_navigation_graph_cache = cache
        graph = cache.get(key)
        if graph is None:
            graph = self._build_graph(world, bounds)
            cache[key] = graph
            # A world can retain only a handful of local regions per setting.
            while len(cache) > 6:
                cache.pop(next(iter(cache)))
        self._world_graph_cache = (id(world), graph, getattr(world, "navigation_revision", 0))
        return graph

    def find_path(self, world, start, target):
        """Return an explicit complete, useful partial, or unreachable result."""
        p = self.physics
        bounds = self._bounds(start, target, world)
        graph = self._graph(world, bounds)
        nodes = graph.nodes

        start_node = self._node_at(world, *start)
        if start_node not in nodes:
            # A route must begin at the character's real standing position;
            # snapping to a remote platform would make the plan fictitious.
            return PathResult(PathStatus.UNREACHABLE)

        target_x, target_y = target
        target_top = target_y-p.height/2
        def heuristic(node):
            x, y = self._position(node)
            return (abs(x+p.width/2-target_x)/p.tile_size +
                    abs(y+p.height/2-target_y)/p.tile_size*1.25)

        def is_goal(node):
            x, y = self._position(node)
            vertical_overlap = y+p.height > target_top+6 and y+p.height/2 < target_top+p.height-6
            return (abs(x+p.width/2-target_x) <= p.tile_size and
                    vertical_overlap and
                    line_clear(world, (x+p.width/2, y+p.height/2), target,
                               p.tile_size))

        def walk_cost(a, b):
            return abs(a[0]-b[0]) * (1.0+self._risk(world, a)*.15)

        def walk_steps(a, b):
            if a == b:
                return []
            direction = 1 if b[0] > a[0] else -1
            output = []
            current = a
            for col in range(a[0]+direction, b[0]+direction, direction):
                node = (col, a[1])
                x, y = self._position(node)
                output.append(NavStep(x, y, "walk", *self._position(current),
                                      (current, node, "walk")))
                current = node
            return output

        start_platform = graph.platform_by_node[start_node]
        platform_heuristic = {
            index: min(heuristic(node) for node in nodes_in_platform)
            for index, nodes_in_platform in enumerate(graph.platforms)
        }
        serial = itertools.count()
        queue = [(platform_heuristic[start_platform], next(serial), start_platform)]
        costs = {start_platform: 0.0}
        entries = {start_platform: start_node}
        parent = {}
        closed = set()
        best_platform, best_node = start_platform, start_node
        best_score = heuristic(start_node)
        reached_platform = reached_node = None
        expansions = 0
        while queue and expansions < self.settings.max_expansions:
            _, _, current_platform = heapq.heappop(queue)
            if current_platform in closed:
                continue
            closed.add(current_platform)
            expansions += 1
            entry = entries[current_platform]
            current_cost = costs[current_platform]

            for candidate in graph.platforms[current_platform]:
                route_cost = current_cost+walk_cost(entry, candidate)
                candidate_score = heuristic(candidate)+route_cost*.12
                if candidate_score < best_score-.05:
                    best_platform, best_node, best_score = (
                        current_platform, candidate, candidate_score)
                if is_goal(candidate):
                    if (reached_platform is None or
                            route_cost < costs.get(reached_platform, math.inf)):
                        reached_platform, reached_node = current_platform, candidate

            if reached_platform is not None:
                break

            for source, edge in graph.platform_edges[current_platform]:
                edge_id = (source, edge.destination, edge.action)
                if edge_id in self._failed_edges:
                    continue
                neighbor_platform = graph.platform_by_node[edge.destination]
                if neighbor_platform in closed:
                    continue
                tentative = current_cost+walk_cost(entry, source)+edge.cost
                if tentative >= costs.get(neighbor_platform, math.inf):
                    continue
                costs[neighbor_platform] = tentative
                entries[neighbor_platform] = edge.destination
                parent[neighbor_platform] = (current_platform, source, edge)
                heapq.heappush(queue, (tentative+platform_heuristic[neighbor_platform],
                                       next(serial), neighbor_platform))

        complete = reached_platform is not None
        destination_platform = reached_platform if complete else best_platform
        destination_node = reached_node if complete else best_node
        if destination_platform == start_platform:
            # If bounded A* did not expand a useful transition, still take one
            # proven local step toward a safer, closer platform. This is a
            # common recovery from a one-tile perch above an open floor.
            local_options = []
            for source, edge in graph.platform_edges[start_platform]:
                edge_id = (source, edge.destination, edge.action)
                if edge_id in self._failed_edges:
                    continue
                progress = heuristic(best_node)-heuristic(edge.destination)
                if progress <= .05:
                    continue
                score = (heuristic(edge.destination) +
                         walk_cost(best_node, source)*.12 + edge.cost*.12)
                # When the goal is below, a validated drop is usually the
                # safest direct way off a perch. Prefer it over a speculative
                # jump when both transitions make comparable progress.
                _, source_y = self._position(best_node)
                _, landing_y = self._position(edge.destination)
                if (edge.action == "drop" and target[1] > source_y and
                        landing_y > source_y):
                    score -= 5.0
                local_options.append((score, source, edge))
            if local_options:
                _, source, edge = min(local_options, key=lambda option: option[0])
                chain = walk_steps(start_node, best_node)
                chain.extend(walk_steps(best_node, source))
                x, y = self._position(edge.destination)
                chain.append(NavStep(x, y, edge.action, edge.takeoff[0],
                    edge.takeoff[1], (source, edge.destination, edge.action)))
                return PathResult(PathStatus.PARTIAL, tuple(chain),
                                  self._position(edge.destination), expansions)
        if destination_platform == start_platform and destination_node == start_node:
            status = PathStatus.COMPLETE if complete else PathStatus.UNREACHABLE
            return PathResult(status, endpoint=self._position(destination_node),
                              expansions=expansions)

        transitions = []
        cursor = destination_platform
        while cursor != start_platform:
            previous, source, edge = parent[cursor]
            transitions.append((previous, source, edge))
            cursor = previous
        transitions.reverse()

        chain = []
        current_node = start_node
        for _, source, edge in transitions:
            chain.extend(walk_steps(current_node, source))
            x, y = self._position(edge.destination)
            edge_id = (source, edge.destination, edge.action)
            chain.append(NavStep(x, y, edge.action, edge.takeoff[0],
                                 edge.takeoff[1], edge_id))
            current_node = edge.destination
        chain.extend(walk_steps(current_node, destination_node))
        endpoint = self._position(destination_node)
        status = PathStatus.COMPLETE if complete else PathStatus.PARTIAL
        return PathResult(status, tuple(chain), endpoint, expansions)
