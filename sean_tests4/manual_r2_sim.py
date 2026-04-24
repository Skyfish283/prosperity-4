"""
Monte Carlo allocator for the Round 2 XIREC expansion puzzle.

The problem statement from the screenshot is modelled as:

PnL = Research * Scale * Speed - Budget_Used

with:
- Research(r) = 200_000 * log(1 + r) / log(101)
- Scale(s) = 7 * s / 100
- Speed(v) = expected rank-based multiplier from Monte Carlo sampling of
  other players' speed allocations
- Budget_Used = budget * (r + s + v) / 100

The script searches the feasible allocation grid where:
- r, s, v are percentage allocations in [0, 100]
- r + s + v <= 100

Outputs:
- One subdirectory per candidate beta prior, each containing:
  - A 2D SVG heatmap with research on the x-axis and scale on the y-axis.
  - A CSV with the best speed choice for every (research, scale) cell.
  - A CSV with the expected speed multiplier by speed allocation.
  - A 3D SVG allocation plot when the optimal point does not spend the full
    XIREC budget.
- A root-level CSV comparing the best allocation across candidate beta priors.

Example:
    python sean_tests4/manual_r2_sim.py --trials 10000 --competitors 20
"""

from __future__ import annotations

import argparse
import csv
import heapq
import html
import math
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


DEFAULT_BUDGET = 50_000.0
DEFAULT_COMPETITORS = 20
DEFAULT_TRIALS = 10_000
DEFAULT_STEP = 1
DEFAULT_BETA_ALPHA = 2.0
DEFAULT_BETA_BETA = 2.0
DEFAULT_BETA_CANDIDATES = (
    (2.0, 2.0),
    (3.0, 2.0),
    (2.0, 3.0),
    (5.0, 5.0),
    (0.7, 0.7),
)
DEFAULT_TOP_K_3D = 2_500


@dataclass(frozen=True)
class SimulationConfig:
    budget: float
    competitors: int
    trials: int
    step: int
    seed: int
    distribution: str
    beta_alpha: float
    beta_beta: float
    beta_candidates: Tuple[Tuple[float, float], ...]
    output_dir: Path
    top_k_3d: int


@dataclass(frozen=True)
class AllocationResult:
    research_pct: int
    scale_pct: int
    speed_pct: int
    used_pct: int
    expected_speed_multiplier: float
    expected_pnl: float
    gross_pnl: float


@dataclass(frozen=True)
class SimulationRunSummary:
    label: str
    best_result: AllocationResult
    heatmap_path: Path
    surface_path: Path
    speed_curve_path: Path
    plot_3d_path: Path | None


def parse_beta_candidate(raw_value: str) -> Tuple[float, float]:
    parts = [part.strip() for part in raw_value.split(",")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid beta candidate '{raw_value}'. Use the form ALPHA,BETA, for example 2,2 or 0.7,0.7."
        )

    try:
        alpha = float(parts[0])
        beta = float(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"Invalid beta candidate '{raw_value}'. Alpha and beta must both be numeric."
        ) from exc

    if alpha <= 0 or beta <= 0:
        raise ValueError(
            f"Invalid beta candidate '{raw_value}'. Alpha and beta must both be positive."
        )

    return alpha, beta


def resolve_beta_candidates(
    raw_candidates: Sequence[str] | None,
    beta_alpha: float | None,
    beta_beta: float | None,
) -> Tuple[Tuple[float, float], ...]:
    if raw_candidates:
        candidates = tuple(parse_beta_candidate(raw_candidate) for raw_candidate in raw_candidates)
    elif beta_alpha is not None or beta_beta is not None:
        candidates = ((beta_alpha if beta_alpha is not None else DEFAULT_BETA_ALPHA,
                       beta_beta if beta_beta is not None else DEFAULT_BETA_BETA),)
    else:
        candidates = DEFAULT_BETA_CANDIDATES

    deduped: List[Tuple[float, float]] = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        deduped.append(candidate)
        seen.add(candidate)

    return tuple(deduped)


def format_float_for_label(value: float) -> str:
    text = f"{value:.6g}"
    return text.replace("-", "m").replace(".", "p")


def simulation_label(config: SimulationConfig) -> str:
    if config.distribution == "beta":
        return f"beta(alpha={config.beta_alpha:g}, beta={config.beta_beta:g})"
    return config.distribution


def simulation_slug(config: SimulationConfig) -> str:
    if config.distribution == "beta":
        return f"beta_a{format_float_for_label(config.beta_alpha)}_b{format_float_for_label(config.beta_beta)}"
    return config.distribution


def parse_args() -> SimulationConfig:
    parser = argparse.ArgumentParser(
        description="Monte Carlo search for the research/scale/speed XIREC allocation puzzle."
    )
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="Total XIREC budget.")
    parser.add_argument(
        "--competitors",
        type=int,
        default=DEFAULT_COMPETITORS,
        help="Number of other players in the speed ranking.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help="Monte Carlo trials used to estimate the speed multiplier curve.",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=DEFAULT_STEP,
        help="Grid step in percentage points. Must divide 100.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="RNG seed for reproducible Monte Carlo sampling.",
    )
    parser.add_argument(
        "--distribution",
        choices=("beta", "uniform", "triangular"),
        default="beta",
        help="Distribution used for competitor speed allocations.",
    )
    parser.add_argument(
        "--beta-alpha",
        type=float,
        default=None,
        help="Alpha parameter for a single beta run when --beta-candidates is not provided.",
    )
    parser.add_argument(
        "--beta-beta",
        type=float,
        default=None,
        help="Beta parameter for a single beta run when --beta-candidates is not provided.",
    )
    parser.add_argument(
        "--beta-candidates",
        nargs="+",
        default=None,
        metavar="ALPHA,BETA",
        help=(
            "One or more beta priors to test in a single batch run. "
            "Example: --beta-candidates 2,2 3,2 2,3"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("manual_r2_sim_outputs"),
        help="Directory for generated SVG and CSV artifacts.",
    )
    parser.add_argument(
        "--top-k-3d",
        type=int,
        default=DEFAULT_TOP_K_3D,
        help="How many top allocations to keep in the optional 3D plot.",
    )
    args = parser.parse_args()

    if args.step <= 0:
        raise ValueError("--step must be positive.")
    if 100 % args.step != 0:
        raise ValueError("--step must divide 100 so the grid can reach 100 exactly.")
    if args.competitors < 0:
        raise ValueError("--competitors cannot be negative.")
    if args.trials <= 0:
        raise ValueError("--trials must be positive.")
    if args.top_k_3d <= 0:
        raise ValueError("--top-k-3d must be positive.")

    if args.beta_alpha is not None and args.beta_alpha <= 0:
        raise ValueError("--beta-alpha must be positive.")
    if args.beta_beta is not None and args.beta_beta <= 0:
        raise ValueError("--beta-beta must be positive.")
    if args.distribution != "beta" and args.beta_candidates:
        raise ValueError("--beta-candidates can only be used with --distribution beta.")
    if args.distribution != "beta" and (args.beta_alpha is not None or args.beta_beta is not None):
        raise ValueError("--beta-alpha and --beta-beta can only be used with --distribution beta.")

    beta_candidates: Tuple[Tuple[float, float], ...] = ()
    beta_alpha = DEFAULT_BETA_ALPHA
    beta_beta = DEFAULT_BETA_BETA
    if args.distribution == "beta":
        beta_candidates = resolve_beta_candidates(args.beta_candidates, args.beta_alpha, args.beta_beta)
        beta_alpha, beta_beta = beta_candidates[0]

    return SimulationConfig(
        budget=args.budget,
        competitors=args.competitors,
        trials=args.trials,
        step=args.step,
        seed=args.seed,
        distribution=args.distribution,
        beta_alpha=beta_alpha,
        beta_beta=beta_beta,
        beta_candidates=beta_candidates,
        output_dir=args.output_dir,
        top_k_3d=args.top_k_3d,
    )


def allocation_levels(step: int) -> List[int]:
    return list(range(0, 101, step))


def research_value(research_pct: int) -> float:
    return 200_000.0 * math.log1p(research_pct) / math.log(101.0)


def scale_value(scale_pct: int) -> float:
    return 7.0 * scale_pct / 100.0


def budget_used(budget: float, used_pct: int) -> float:
    return budget * used_pct / 100.0


def speed_multiplier_from_rank(rank: int, total_players: int) -> float:
    if total_players <= 1:
        return 0.9
    return 0.9 - 0.8 * (rank - 1) / (total_players - 1)


def snap_to_level(raw_value: float, step: int) -> int:
    snapped = int(round(raw_value / step) * step)
    return max(0, min(100, snapped))


def sample_competitor_speed(config: SimulationConfig, rng: random.Random) -> int:
    if config.distribution == "beta":
        raw = 100.0 * rng.betavariate(config.beta_alpha, config.beta_beta)
    elif config.distribution == "uniform":
        raw = 100.0 * rng.random()
    else:
        raw = rng.triangular(0.0, 100.0, 50.0)
    return snap_to_level(raw, config.step)


def estimate_speed_expectations(config: SimulationConfig) -> Dict[int, float]:
    levels = allocation_levels(config.step)
    totals = {speed: 0.0 for speed in levels}
    total_players = config.competitors + 1

    if config.competitors == 0:
        return {speed: 0.9 for speed in levels}

    rng = random.Random(config.seed)

    for _ in range(config.trials):
        frequency = {speed: 0 for speed in levels}
        for _ in range(config.competitors):
            frequency[sample_competitor_speed(config, rng)] += 1

        higher_count = 0
        for speed in reversed(levels):
            rank = 1 + higher_count
            totals[speed] += speed_multiplier_from_rank(rank, total_players)
            higher_count += frequency[speed]

    return {speed: totals[speed] / config.trials for speed in levels}


def maybe_push_top_allocation(
    heap: List[Tuple[float, int, int, int, AllocationResult]],
    result: AllocationResult,
    limit: int,
) -> None:
    entry = (result.expected_pnl, result.research_pct, result.scale_pct, result.speed_pct, result)
    if len(heap) < limit:
        heapq.heappush(heap, entry)
        return
    if entry > heap[0]:
        heapq.heapreplace(heap, entry)


def evaluate_surface(
    config: SimulationConfig,
    speed_expectations: Dict[int, float],
) -> Tuple[Dict[Tuple[int, int], AllocationResult], AllocationResult, List[AllocationResult]]:
    levels = allocation_levels(config.step)
    surface: Dict[Tuple[int, int], AllocationResult] = {}
    best_result: AllocationResult | None = None
    top_allocations_heap: List[Tuple[float, int, int, int, AllocationResult]] = []

    for research_pct in levels:
        research_score = research_value(research_pct)
        for scale_pct in levels:
            if research_pct + scale_pct > 100:
                continue

            scale_score_value = scale_value(scale_pct)
            best_for_cell: AllocationResult | None = None
            max_speed_pct = 100 - research_pct - scale_pct

            for speed_pct in levels:
                if speed_pct > max_speed_pct:
                    break

                used_pct = research_pct + scale_pct + speed_pct
                speed_multiplier = speed_expectations[speed_pct]
                gross_pnl = research_score * scale_score_value * speed_multiplier
                expected_pnl = gross_pnl - budget_used(config.budget, used_pct)
                result = AllocationResult(
                    research_pct=research_pct,
                    scale_pct=scale_pct,
                    speed_pct=speed_pct,
                    used_pct=used_pct,
                    expected_speed_multiplier=speed_multiplier,
                    expected_pnl=expected_pnl,
                    gross_pnl=gross_pnl,
                )

                if best_for_cell is None or result.expected_pnl > best_for_cell.expected_pnl:
                    best_for_cell = result

                maybe_push_top_allocation(top_allocations_heap, result, config.top_k_3d)

                if best_result is None or result.expected_pnl > best_result.expected_pnl:
                    best_result = result

            if best_for_cell is None:
                continue
            surface[(research_pct, scale_pct)] = best_for_cell

    if best_result is None:
        raise RuntimeError("No feasible allocations were evaluated.")

    top_allocations = [entry[-1] for entry in sorted(top_allocations_heap, reverse=True)]
    return surface, best_result, top_allocations


def candidate_configs(base_config: SimulationConfig) -> List[SimulationConfig]:
    if base_config.distribution != "beta":
        return [base_config]

    configs: List[SimulationConfig] = []
    use_subdirectories = len(base_config.beta_candidates) > 1
    for beta_alpha, beta_beta in base_config.beta_candidates:
        run_config = replace(
            base_config,
            beta_alpha=beta_alpha,
            beta_beta=beta_beta,
            beta_candidates=(),
        )
        if use_subdirectories:
            run_config = replace(
                run_config,
                output_dir=base_config.output_dir / simulation_slug(run_config),
            )
        configs.append(
            run_config
        )
    return configs


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(color_a: Tuple[int, int, int], color_b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(round(lerp(color_a[0], color_b[0], t))),
        int(round(lerp(color_a[1], color_b[1], t))),
        int(round(lerp(color_a[2], color_b[2], t))),
    )


def color_for_value(value: float, min_value: float, max_value: float) -> str:
    if math.isclose(min_value, max_value):
        rgb = (255, 196, 61)
        return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"

    normalized = (value - min_value) / (max_value - min_value)
    stops = [
        (0.0, (27, 38, 59)),
        (0.35, (44, 123, 182)),
        (0.65, (255, 199, 95)),
        (1.0, (200, 48, 59)),
    ]

    for idx in range(1, len(stops)):
        left_pos, left_color = stops[idx - 1]
        right_pos, right_color = stops[idx]
        if normalized <= right_pos:
            local_t = (normalized - left_pos) / (right_pos - left_pos) if right_pos > left_pos else 0.0
            rgb = lerp_color(left_color, right_color, local_t)
            return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"

    rgb = stops[-1][1]
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def write_surface_csv(
    surface: Dict[Tuple[int, int], AllocationResult],
    config: SimulationConfig,
) -> Path:
    output_path = config.output_dir / "research_scale_surface.csv"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "research_pct",
                "scale_pct",
                "best_speed_pct",
                "used_pct",
                "expected_speed_multiplier",
                "gross_pnl",
                "expected_pnl",
            ]
        )
        for key in sorted(surface):
            result = surface[key]
            writer.writerow(
                [
                    result.research_pct,
                    result.scale_pct,
                    result.speed_pct,
                    result.used_pct,
                    f"{result.expected_speed_multiplier:.6f}",
                    f"{result.gross_pnl:.2f}",
                    f"{result.expected_pnl:.2f}",
                ]
            )
    return output_path


def write_speed_curve_csv(
    speed_expectations: Dict[int, float],
    config: SimulationConfig,
) -> Path:
    output_path = config.output_dir / "speed_curve.csv"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["speed_pct", "expected_speed_multiplier"])
        for speed_pct in allocation_levels(config.step):
            writer.writerow([speed_pct, f"{speed_expectations[speed_pct]:.6f}"])
    return output_path


def write_batch_summary_csv(
    run_summaries: Sequence[SimulationRunSummary],
    root_output_dir: Path,
    budget: float,
) -> Path:
    output_path = root_output_dir / "beta_candidate_summary.csv"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "candidate",
                "research_pct",
                "scale_pct",
                "speed_pct",
                "used_pct",
                "used_budget",
                "unused_budget",
                "expected_speed_multiplier",
                "gross_pnl",
                "expected_pnl",
                "heatmap_path",
                "surface_path",
                "speed_curve_path",
                "plot_3d_path",
            ]
        )
        for run_summary in run_summaries:
            result = run_summary.best_result
            used_budget = budget_used(budget, result.used_pct)
            writer.writerow(
                [
                    run_summary.label,
                    result.research_pct,
                    result.scale_pct,
                    result.speed_pct,
                    result.used_pct,
                    f"{used_budget:.2f}",
                    f"{budget - used_budget:.2f}",
                    f"{result.expected_speed_multiplier:.6f}",
                    f"{result.gross_pnl:.2f}",
                    f"{result.expected_pnl:.2f}",
                    str(run_summary.heatmap_path.relative_to(root_output_dir)),
                    str(run_summary.surface_path.relative_to(root_output_dir)),
                    str(run_summary.speed_curve_path.relative_to(root_output_dir)),
                    (
                        str(run_summary.plot_3d_path.relative_to(root_output_dir))
                        if run_summary.plot_3d_path is not None
                        else ""
                    ),
                ]
            )
    return output_path


def render_heatmap_svg(
    surface: Dict[Tuple[int, int], AllocationResult],
    best_result: AllocationResult,
    config: SimulationConfig,
) -> Path:
    levels = allocation_levels(config.step)
    values = [result.expected_pnl for result in surface.values()]
    min_value = min(values)
    max_value = max(values)

    width = 1180
    height = 980
    margin_left = 110
    margin_right = 240
    margin_top = 90
    margin_bottom = 110
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    cell_width = plot_width / len(levels)
    cell_height = plot_height / len(levels)

    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0f1720"/>',
        '<style>',
        "text { font-family: Arial, sans-serif; fill: #e5eef8; }",
        ".muted { fill: #9fb3c8; }",
        ".axis { stroke: #c7d3df; stroke-width: 1.4; }",
        ".grid { stroke: #233548; stroke-width: 1; }",
        ".legend-text { font-size: 13px; }",
        "</style>",
        '<text x="110" y="48" font-size="28" font-weight="700">Research vs Scale Heatmap</text>',
        (
            '<text x="110" y="74" font-size="15" class="muted">'
            f"Assumption: {html.escape(simulation_label(config))}"
            "</text>"
        ),
        (
            '<text x="110" y="96" font-size="15" class="muted">'
            "Color = best expected PnL after optimizing speed on the remaining budget."
            "</text>"
        ),
        (
            f'<text x="{width - margin_right + 8}" y="126" font-size="16" font-weight="700">Best allocation</text>'
        ),
    ]

    info_lines = [
        f"Research: {best_result.research_pct}%",
        f"Scale: {best_result.scale_pct}%",
        f"Speed: {best_result.speed_pct}%",
        f"Used budget: {budget_used(config.budget, best_result.used_pct):,.0f} XIRECs",
        f"Unused budget: {config.budget - budget_used(config.budget, best_result.used_pct):,.0f} XIRECs",
        f"Expected speed multiplier: {best_result.expected_speed_multiplier:.4f}",
        f"Expected PnL: {best_result.expected_pnl:,.2f}",
    ]
    for idx, line in enumerate(info_lines):
        svg.append(
            f'<text x="{width - margin_right + 8}" y="{158 + idx * 24}" font-size="15">{html.escape(line)}</text>'
        )

    for research_pct in levels:
        x = margin_left + research_pct / config.step * cell_width
        svg.append(f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{height - margin_bottom}" class="grid"/>')
    for scale_pct in levels:
        y = margin_top + plot_height - scale_pct / config.step * cell_height
        svg.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" class="grid"/>')

    for (research_pct, scale_pct), result in sorted(surface.items()):
        x = margin_left + research_pct / config.step * cell_width
        y = margin_top + plot_height - (scale_pct / config.step + 1) * cell_height
        tooltip = html.escape(
            "\n".join(
                [
                    f"Research: {research_pct}%",
                    f"Scale: {scale_pct}%",
                    f"Best speed: {result.speed_pct}%",
                    f"Budget used: {budget_used(config.budget, result.used_pct):,.0f}",
                    f"Expected speed multiplier: {result.expected_speed_multiplier:.4f}",
                    f"Expected PnL: {result.expected_pnl:,.2f}",
                ]
            )
        )
        fill = color_for_value(result.expected_pnl, min_value, max_value)
        svg.append(
            (
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_width:.2f}" height="{cell_height:.2f}" '
                f'fill="{fill}" stroke="none"><title>{tooltip}</title></rect>'
            )
        )

    svg.extend(
        [
            f'<line x1="{margin_left}" y1="{height - margin_bottom}" x2="{margin_left + plot_width}" y2="{height - margin_bottom}" class="axis"/>',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" class="axis"/>',
        ]
    )

    for tick in range(0, 101, 10):
        x = margin_left + tick / 100.0 * plot_width
        y = margin_top + plot_height - tick / 100.0 * plot_height
        svg.append(f'<line x1="{x:.2f}" y1="{height - margin_bottom}" x2="{x:.2f}" y2="{height - margin_bottom + 7}" class="axis"/>')
        svg.append(f'<text x="{x:.2f}" y="{height - margin_bottom + 28}" font-size="13" text-anchor="middle">{tick}</text>')
        svg.append(f'<line x1="{margin_left - 7}" y1="{y:.2f}" x2="{margin_left}" y2="{y:.2f}" class="axis"/>')
        svg.append(f'<text x="{margin_left - 16}" y="{y + 4:.2f}" font-size="13" text-anchor="end">{tick}</text>')

    svg.extend(
        [
            f'<text x="{margin_left + plot_width / 2:.2f}" y="{height - 34}" font-size="18" text-anchor="middle">Research allocation (%)</text>',
            (
                f'<text x="32" y="{margin_top + plot_height / 2:.2f}" font-size="18" '
                'text-anchor="middle" transform="rotate(-90 32 '
                f'{margin_top + plot_height / 2:.2f})">Scale allocation (%)</text>'
            ),
        ]
    )

    marker_x = margin_left + best_result.research_pct / config.step * cell_width + cell_width / 2
    marker_y = margin_top + plot_height - (best_result.scale_pct / config.step + 0.5) * cell_height
    svg.extend(
        [
            f'<circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="7" fill="none" stroke="#ffffff" stroke-width="2.5"/>',
            f'<circle cx="{marker_x:.2f}" cy="{marker_y:.2f}" r="2.8" fill="#ffffff"/>',
        ]
    )

    legend_x = width - margin_right + 36
    legend_y = 330
    legend_height = 280
    legend_steps = 100
    for idx in range(legend_steps):
        t0 = idx / legend_steps
        value = lerp(max_value, min_value, t0)
        y = legend_y + idx * (legend_height / legend_steps)
        color = color_for_value(value, min_value, max_value)
        svg.append(
            f'<rect x="{legend_x}" y="{y:.2f}" width="30" height="{legend_height / legend_steps + 1:.2f}" fill="{color}" stroke="none"/>'
        )
    svg.extend(
        [
            f'<rect x="{legend_x}" y="{legend_y}" width="30" height="{legend_height}" fill="none" stroke="#d7e4ef" stroke-width="1"/>',
            f'<text x="{legend_x + 44}" y="{legend_y + 4}" class="legend-text">{max_value:,.0f}</text>',
            f'<text x="{legend_x + 44}" y="{legend_y + legend_height / 2 + 4:.2f}" class="legend-text">{(min_value + max_value) / 2:,.0f}</text>',
            f'<text x="{legend_x + 44}" y="{legend_y + legend_height + 4}" class="legend-text">{min_value:,.0f}</text>',
            f'<text x="{legend_x - 4}" y="{legend_y - 14}" font-size="14" font-weight="700">Expected PnL</text>',
        ]
    )

    svg.append("</svg>")

    output_path = config.output_dir / "research_scale_heatmap.svg"
    output_path.write_text("\n".join(svg), encoding="utf-8")
    return output_path


def project_point(
    research_pct: float,
    scale_pct: float,
    speed_pct: float,
    origin_x: float,
    origin_y: float,
    unit_x: float,
    unit_y: float,
    vertical_unit: float,
) -> Tuple[float, float]:
    x = origin_x + (research_pct - scale_pct) * unit_x
    y = origin_y - speed_pct * vertical_unit + (research_pct + scale_pct) * unit_y
    return x, y


def svg_polyline(points: Sequence[Tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def render_3d_svg(
    top_allocations: Sequence[AllocationResult],
    best_result: AllocationResult,
    config: SimulationConfig,
) -> Path:
    width = 1180
    height = 980
    origin_x = 590.0
    origin_y = 760.0
    unit_x = 4.2
    unit_y = 2.1
    vertical_unit = 4.35

    values = [result.expected_pnl for result in top_allocations]
    min_value = min(values)
    max_value = max(values)

    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0f1720"/>',
        '<style>',
        "text { font-family: Arial, sans-serif; fill: #e5eef8; }",
        ".muted { fill: #9fb3c8; }",
        ".wire { fill: none; stroke: #7fa5c8; stroke-width: 1.4; opacity: 0.8; }",
        ".plane { fill: #7eb8ff; fill-opacity: 0.08; stroke: #4b78a8; stroke-width: 1.4; }",
        ".axis-label { font-size: 17px; font-weight: 700; }",
        "</style>",
        '<text x="80" y="48" font-size="28" font-weight="700">3D Allocation Landscape</text>',
        (
            '<text x="80" y="74" font-size="15" class="muted">'
            f"Assumption: {html.escape(simulation_label(config))}"
            "</text>"
        ),
        (
            '<text x="80" y="96" font-size="15" class="muted">'
            "Only emitted because the best solution does not spend the full XIREC budget."
            "</text>"
        ),
    ]

    origin = project_point(0, 0, 0, origin_x, origin_y, unit_x, unit_y, vertical_unit)
    research_vertex = project_point(100, 0, 0, origin_x, origin_y, unit_x, unit_y, vertical_unit)
    scale_vertex = project_point(0, 100, 0, origin_x, origin_y, unit_x, unit_y, vertical_unit)
    speed_vertex = project_point(0, 0, 100, origin_x, origin_y, unit_x, unit_y, vertical_unit)

    svg.append(
        f'<polygon points="{svg_polyline([research_vertex, scale_vertex, speed_vertex])}" class="plane"/>'
    )

    edges = [
        (origin, research_vertex),
        (origin, scale_vertex),
        (origin, speed_vertex),
        (research_vertex, scale_vertex),
        (research_vertex, speed_vertex),
        (scale_vertex, speed_vertex),
    ]
    for start, end in edges:
        svg.append(f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" class="wire"/>')

    svg.extend(
        [
            f'<text x="{research_vertex[0] + 18:.2f}" y="{research_vertex[1] + 10:.2f}" class="axis-label">Research</text>',
            f'<text x="{scale_vertex[0] - 100:.2f}" y="{scale_vertex[1] + 10:.2f}" class="axis-label">Scale</text>',
            f'<text x="{speed_vertex[0] + 16:.2f}" y="{speed_vertex[1] - 8:.2f}" class="axis-label">Speed</text>',
            f'<text x="{origin[0] - 8:.2f}" y="{origin[1] + 22:.2f}" font-size="14" class="muted">0%</text>',
            f'<text x="{research_vertex[0] + 8:.2f}" y="{research_vertex[1] + 28:.2f}" font-size="14" class="muted">100%</text>',
            f'<text x="{scale_vertex[0] - 24:.2f}" y="{scale_vertex[1] + 28:.2f}" font-size="14" class="muted">100%</text>',
            f'<text x="{speed_vertex[0] + 10:.2f}" y="{speed_vertex[1] - 22:.2f}" font-size="14" class="muted">100%</text>',
        ]
    )

    sorted_points = sorted(top_allocations, key=lambda result: (result.speed_pct, result.research_pct + result.scale_pct))
    for result in sorted_points:
        x, y = project_point(
            result.research_pct,
            result.scale_pct,
            result.speed_pct,
            origin_x,
            origin_y,
            unit_x,
            unit_y,
            vertical_unit,
        )
        radius = 2.0 + 2.4 * max(0.0, (result.expected_pnl - min_value) / (max_value - min_value or 1.0))
        color = color_for_value(result.expected_pnl, min_value, max_value)
        tooltip = html.escape(
            "\n".join(
                [
                    f"Research: {result.research_pct}%",
                    f"Scale: {result.scale_pct}%",
                    f"Speed: {result.speed_pct}%",
                    f"Used budget: {budget_used(config.budget, result.used_pct):,.0f}",
                    f"Expected PnL: {result.expected_pnl:,.2f}",
                ]
            )
        )
        svg.append(
            (
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" fill-opacity="0.85" '
                f'stroke="#ffffff" stroke-opacity="0.10" stroke-width="0.8"><title>{tooltip}</title></circle>'
            )
        )

    best_x, best_y = project_point(
        best_result.research_pct,
        best_result.scale_pct,
        best_result.speed_pct,
        origin_x,
        origin_y,
        unit_x,
        unit_y,
        vertical_unit,
    )
    svg.extend(
        [
            f'<circle cx="{best_x:.2f}" cy="{best_y:.2f}" r="7.5" fill="none" stroke="#ffffff" stroke-width="2.4"/>',
            f'<circle cx="{best_x:.2f}" cy="{best_y:.2f}" r="2.8" fill="#ffffff"/>',
            (
                f'<text x="{best_x + 16:.2f}" y="{best_y - 12:.2f}" font-size="15" font-weight="700">'
                "Best interior allocation</text>"
            ),
        ]
    )

    summary_x = 80
    summary_y = 136
    summary_lines = [
        f"Research = {best_result.research_pct}%",
        f"Scale = {best_result.scale_pct}%",
        f"Speed = {best_result.speed_pct}%",
        f"Budget used = {budget_used(config.budget, best_result.used_pct):,.0f} / {config.budget:,.0f}",
        f"Unused budget = {config.budget - budget_used(config.budget, best_result.used_pct):,.0f}",
        f"Expected PnL = {best_result.expected_pnl:,.2f}",
    ]
    for idx, line in enumerate(summary_lines):
        svg.append(f'<text x="{summary_x}" y="{summary_y + idx * 22}" font-size="15">{html.escape(line)}</text>')

    legend_x = 1040
    legend_y = 170
    legend_height = 320
    legend_steps = 100
    for idx in range(legend_steps):
        t0 = idx / legend_steps
        value = lerp(max_value, min_value, t0)
        y = legend_y + idx * (legend_height / legend_steps)
        color = color_for_value(value, min_value, max_value)
        svg.append(
            f'<rect x="{legend_x}" y="{y:.2f}" width="28" height="{legend_height / legend_steps + 1:.2f}" fill="{color}" stroke="none"/>'
        )
    svg.extend(
        [
            f'<rect x="{legend_x}" y="{legend_y}" width="28" height="{legend_height}" fill="none" stroke="#d7e4ef" stroke-width="1"/>',
            f'<text x="{legend_x - 6}" y="{legend_y - 14}" font-size="14" font-weight="700">Expected PnL</text>',
            f'<text x="{legend_x + 40}" y="{legend_y + 4}" font-size="13">{max_value:,.0f}</text>',
            f'<text x="{legend_x + 40}" y="{legend_y + legend_height / 2 + 4:.2f}" font-size="13">{(min_value + max_value) / 2:,.0f}</text>',
            f'<text x="{legend_x + 40}" y="{legend_y + legend_height + 4}" font-size="13">{min_value:,.0f}</text>',
        ]
    )

    svg.append("</svg>")

    output_path = config.output_dir / "allocation_landscape_3d.svg"
    output_path.write_text("\n".join(svg), encoding="utf-8")
    return output_path


def run_simulation(config: SimulationConfig) -> Tuple[SimulationRunSummary, Dict[int, float]]:
    config.output_dir.mkdir(parents=True, exist_ok=True)

    speed_expectations = estimate_speed_expectations(config)
    surface, best_result, top_allocations = evaluate_surface(config, speed_expectations)

    surface_path = write_surface_csv(surface, config)
    speed_curve_path = write_speed_curve_csv(speed_expectations, config)
    heatmap_path = render_heatmap_svg(surface, best_result, config)

    plot_3d_path: Path | None = None
    if best_result.used_pct < 100:
        plot_3d_path = render_3d_svg(top_allocations, best_result, config)

    run_summary = SimulationRunSummary(
        label=simulation_label(config),
        best_result=best_result,
        heatmap_path=heatmap_path,
        surface_path=surface_path,
        speed_curve_path=speed_curve_path,
        plot_3d_path=plot_3d_path,
    )
    return run_summary, speed_expectations


def print_summary(
    run_summary: SimulationRunSummary,
    speed_expectations: Dict[int, float],
    config: SimulationConfig,
    verbose_speed_curve: bool,
) -> None:
    best_result = run_summary.best_result
    used_budget = budget_used(config.budget, best_result.used_pct)
    print(f"Scenario: {run_summary.label}")
    print("Monte Carlo speed curve assumptions")
    print(f"  competitors: {config.competitors}")
    print(f"  trials: {config.trials}")
    print(f"  grid step: {config.step}%")
    print(f"  distribution: {config.distribution}")
    if config.distribution == "beta":
        print(f"  beta(alpha={config.beta_alpha}, beta={config.beta_beta})")
    print()
    print("Best allocation")
    print(f"  research: {best_result.research_pct}%")
    print(f"  scale:    {best_result.scale_pct}%")
    print(f"  speed:    {best_result.speed_pct}%")
    print(f"  used:     {best_result.used_pct}% -> {used_budget:,.0f} XIRECs")
    print(f"  unused:   {config.budget - used_budget:,.0f} XIRECs")
    print(f"  speed EV: {best_result.expected_speed_multiplier:.5f}")
    print(f"  gross:    {best_result.gross_pnl:,.2f}")
    print(f"  pnl:      {best_result.expected_pnl:,.2f}")
    print()
    print("Artifacts")
    print(f"  heatmap: {run_summary.heatmap_path}")
    print(f"  surface: {run_summary.surface_path}")
    print(f"  speed curve: {run_summary.speed_curve_path}")
    if run_summary.plot_3d_path is None:
        print("  3d plot: skipped (best allocation uses the full budget)")
    else:
        print(f"  3d plot: {run_summary.plot_3d_path}")
    if verbose_speed_curve:
        print()
        print("Expected speed multiplier by speed allocation")
        for speed_pct in allocation_levels(config.step):
            print(f"  {speed_pct:>3}% -> {speed_expectations[speed_pct]:.5f}")


def print_batch_summary(run_summaries: Sequence[SimulationRunSummary], summary_csv_path: Path) -> None:
    print()
    print("Beta candidate comparison")
    for run_summary in sorted(run_summaries, key=lambda item: item.best_result.expected_pnl, reverse=True):
        result = run_summary.best_result
        print(
            "  "
            f"{run_summary.label}: pnl={result.expected_pnl:,.2f}, "
            f"alloc=({result.research_pct}%, {result.scale_pct}%, {result.speed_pct}%), "
            f"used={result.used_pct}%"
        )
    print(f"  summary csv: {summary_csv_path}")


def main() -> None:
    config = parse_args()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    run_configs = candidate_configs(config)
    verbose_speed_curve = len(run_configs) == 1
    run_summaries: List[SimulationRunSummary] = []

    for run_config in run_configs:
        run_summary, speed_expectations = run_simulation(run_config)
        print_summary(run_summary, speed_expectations, run_config, verbose_speed_curve=verbose_speed_curve)
        run_summaries.append(run_summary)
        if len(run_configs) > 1:
            print()

    if len(run_summaries) > 1:
        summary_csv_path = write_batch_summary_csv(run_summaries, config.output_dir, config.budget)
        print_batch_summary(run_summaries, summary_csv_path)


if __name__ == "__main__":
    main()
