import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class StrategicStance(str, Enum):
    INNOVATION_LED = "Innovation-led"
    EFFICIENCY_LED = "Efficiency-led"


@dataclass
class MetricSnapshot:
    """Metrics at a specific point in time."""

    revenue_index: float  # Indexed revenue (base year = 1.0)
    market_share: float  # 0.0 - 1.0
    tech_adoption_velocity: float  # 0.0 - 1.0


@dataclass
class TimelineDataPoint:
    """A single data point on the scenario timeline."""

    year: int
    metrics: MetricSnapshot
    label: Optional[str] = None


@dataclass
class BranchOutcome:
    """A possible outcome branching from a turning point."""

    id: str
    label: str
    description: str
    metric_delta: MetricSnapshot
    probability: float  # 0.0 - 1.0
    next_node_id: Optional[str] = None


@dataclass
class TurningPointNode:
    """A decision point where the scenario can branch."""

    id: str
    year: int
    title: str
    description: str
    external_driver: str  # e.g. "NDC adoption", "GenAI breakthrough"
    branches: List[BranchOutcome]


@dataclass
class StrategicProfile:
    """One of the three strategic archetypes for OTA positioning."""

    name: str  # "Cost Leader", "Differentiator", "Niche Search"
    description: str
    ai_adoption_bias: float  # 0.0 - 1.0
    direct_booking_resilience: float  # 0.0 - 1.0
    strategic_stance: StrategicStance


@dataclass
class MatrixPosition:
    """Position in the 2x2+S strategic matrix.

    Axis 1: Airline Direct Booking Dominance (0=low, 1=high)
    Axis 2: AI Agent Adoption (0=low, 1=high)
    Dimension 3: Strategic Orientation (Innovation-led vs Efficiency-led)
    """

    airline_direct_booking_dominance: float
    ai_agent_adoption: float
    strategic_orientation: StrategicStance


@dataclass
class CompetitorProfile:
    """Baseline profile for a specific OTA competitor."""

    name: str
    key_capability: str
    initial_position: MatrixPosition
    default_profile: str  # References StrategicProfile.name
    initial_market_share: float = 0.0  # normalized revenue-share proxy (0..1)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Scenario:
    """Top-level scenario for OTA strategic roadmap simulation."""

    id: str
    name: str
    description: str
    timeline: List[TimelineDataPoint]
    nodes: List[TurningPointNode]
    strategic_profiles: List[StrategicProfile]
    competitors: List[CompetitorProfile]
    metadata: Dict[str, str] = field(default_factory=dict)
    # Per-competitor market-share trajectory across the timeline; populated
    # by Simulator.project_market_shares() during scenario generation.
    # Shape: {"Competitor Name" or "Other": [{"year": int, "share": float}, ...]}
    market_share_projection: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)


def build_sample_scenario() -> Scenario:
    """Build a sample 'AI Leapfrog' scenario with realistic OTA data."""

    # --- Strategic Profiles ---
    profiles = [
        StrategicProfile(
            name="Cost Leader",
            description="Optimizes operations for price-sensitive segments via scale and automation.",
            ai_adoption_bias=0.4,
            direct_booking_resilience=0.3,
            strategic_stance=StrategicStance.EFFICIENCY_LED,
        ),
        StrategicProfile(
            name="Differentiator",
            description="Invests heavily in AI-driven personalization and premium experiences.",
            ai_adoption_bias=0.9,
            direct_booking_resilience=0.7,
            strategic_stance=StrategicStance.INNOVATION_LED,
        ),
        StrategicProfile(
            name="Niche Search",
            description="Focuses on underserved routes and complex itineraries using proprietary technology.",
            ai_adoption_bias=0.7,
            direct_booking_resilience=0.5,
            strategic_stance=StrategicStance.INNOVATION_LED,
        ),
    ]

    # --- Competitor Profiles ---
    # initial_market_share values are normalized revenue-share proxies derived
    # from each firm's most recent public filings (see metadata.source /
    # source_year). Tracked OTAs sum to ~0.65; the remaining ~0.35 is folded
    # into the implicit "Other" bucket at projection time.
    competitors = [
        CompetitorProfile(
            name="Booking Holdings",
            key_capability="Global meta-search + multi-brand scale",
            initial_position=MatrixPosition(0.50, 0.55, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.30,
            metadata={
                "source": "Booking Holdings 2023 10-K",
                "source_year": "2023",
            },
        ),
        CompetitorProfile(
            name="Expedia Group",
            key_capability="Brand portfolio + Trip Planner AI",
            initial_position=MatrixPosition(0.50, 0.60, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.18,
            metadata={
                "source": "Expedia Group 2023 10-K",
                "source_year": "2023",
            },
        ),
        CompetitorProfile(
            name="Trip.com Group",
            key_capability="APAC dominance + TripGenie AI assistant",
            initial_position=MatrixPosition(0.40, 0.70, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.09,
            metadata={
                "source": "Trip.com Group 2023 Annual Report",
                "source_year": "2023",
            },
        ),
        CompetitorProfile(
            name="Agoda",
            key_capability="APAC accommodations + aggressive pricing",
            initial_position=MatrixPosition(0.40, 0.55, StrategicStance.EFFICIENCY_LED),
            default_profile="Cost Leader",
            initial_market_share=0.05,
            metadata={
                "source": "Booking Holdings 2023 10-K (Agoda segment)",
                "source_year": "2023",
            },
        ),
        CompetitorProfile(
            name="eDreams ODIGEO",
            key_capability="Prime Subscription",
            initial_position=MatrixPosition(0.5, 0.5, StrategicStance.EFFICIENCY_LED),
            default_profile="Cost Leader",
            initial_market_share=0.02,
            metadata={
                "source": "eDreams ODIGEO FY2024 Annual Report",
                "source_year": "2024",
            },
        ),
        CompetitorProfile(
            name="Kiwi.com",
            key_capability="Virtual Interlining",
            initial_position=MatrixPosition(0.3, 0.6, StrategicStance.INNOVATION_LED),
            default_profile="Niche Search",
            initial_market_share=0.01,
            metadata={
                "source": "Kiwi.com publicly reported revenue (private, 2023)",
                "source_year": "2023",
            },
        ),
    ]

    # --- Timeline (key years 1990-2040) ---
    timeline = [
        TimelineDataPoint(1990, MetricSnapshot(1.0, 0.02, 0.05), "OTA industry emerges"),
        TimelineDataPoint(1995, MetricSnapshot(1.8, 0.05, 0.10)),
        TimelineDataPoint(2000, MetricSnapshot(4.0, 0.15, 0.20), "Dot-com boom & OTA expansion"),
        TimelineDataPoint(2005, MetricSnapshot(6.5, 0.25, 0.30)),
        TimelineDataPoint(2008, MetricSnapshot(5.8, 0.28, 0.35), "Financial crisis impact"),
        TimelineDataPoint(2010, MetricSnapshot(7.0, 0.30, 0.40), "Mobile booking begins"),
        TimelineDataPoint(2015, MetricSnapshot(10.0, 0.35, 0.50), "Meta-search dominance"),
        TimelineDataPoint(2019, MetricSnapshot(13.0, 0.38, 0.55), "Pre-pandemic peak"),
        TimelineDataPoint(2020, MetricSnapshot(4.5, 0.30, 0.58), "COVID-19 collapse"),
        TimelineDataPoint(2023, MetricSnapshot(11.0, 0.33, 0.65), "Recovery & GenAI emergence"),
        TimelineDataPoint(2025, MetricSnapshot(14.0, 0.35, 0.75), "NDC adoption accelerates"),
        TimelineDataPoint(2028, MetricSnapshot(18.0, 0.38, 0.85)),
        TimelineDataPoint(2030, MetricSnapshot(22.0, 0.40, 0.90), "AI agents reshape booking"),
        TimelineDataPoint(2035, MetricSnapshot(30.0, 0.42, 0.95)),
        TimelineDataPoint(2040, MetricSnapshot(40.0, 0.45, 0.98), "Autonomous travel planning"),
    ]

    # --- Turning Point Nodes ---
    nodes = [
        TurningPointNode(
            id="tp-001",
            year=2025,
            title="NDC Standard Adoption",
            description="Airlines push direct distribution via NDC, threatening OTA intermediation.",
            external_driver="NDC adoption",
            branches=[
                BranchOutcome(
                    id="tp-001-a",
                    label="Embrace NDC",
                    description="Integrate NDC pipelines and offer rich airline content.",
                    metric_delta=MetricSnapshot(0.05, 0.02, 0.10),
                    probability=0.6,
                    next_node_id="tp-002",
                ),
                BranchOutcome(
                    id="tp-001-b",
                    label="Resist NDC",
                    description="Maintain legacy GDS relationships; risk content gaps.",
                    metric_delta=MetricSnapshot(-0.03, -0.04, 0.02),
                    probability=0.4,
                    next_node_id="tp-002",
                ),
            ],
        ),
        TurningPointNode(
            id="tp-002",
            year=2028,
            title="AI Agent Gateway Decision",
            description="Decide whether to build proprietary AI travel agents or partner with platform providers.",
            external_driver="GenAI breakthrough",
            branches=[
                BranchOutcome(
                    id="tp-002-a",
                    label="Build Proprietary AI",
                    description="Heavy R&D investment in in-house AI concierge capabilities.",
                    metric_delta=MetricSnapshot(0.12, 0.06, 0.15),
                    probability=0.35,
                    next_node_id="tp-003",
                ),
                BranchOutcome(
                    id="tp-002-b",
                    label="Partner with AI Platforms",
                    description="Integrate with major AI assistants as a travel fulfillment backend.",
                    metric_delta=MetricSnapshot(0.08, 0.03, 0.12),
                    probability=0.45,
                    next_node_id="tp-003",
                ),
                BranchOutcome(
                    id="tp-002-c",
                    label="Wait and See",
                    description="Minimal AI investment; focus on existing search/book model.",
                    metric_delta=MetricSnapshot(-0.02, -0.05, 0.03),
                    probability=0.20,
                    next_node_id="tp-003",
                ),
            ],
        ),
        TurningPointNode(
            id="tp-003",
            year=2032,
            title="Airline Direct Booking Dominance Tipping Point",
            description="Airlines capture >50% of bookings direct; OTAs must redefine value proposition.",
            external_driver="Airline direct booking dominance",
            branches=[
                BranchOutcome(
                    id="tp-003-a",
                    label="Pivot to Complex Itineraries",
                    description="Focus on multi-city, multi-modal trips that airlines cannot serve directly.",
                    metric_delta=MetricSnapshot(0.10, -0.02, 0.08),
                    probability=0.5,
                ),
                BranchOutcome(
                    id="tp-003-b",
                    label="Become Aggregator Platform",
                    description="Transform into marketplace connecting travelers with suppliers via AI.",
                    metric_delta=MetricSnapshot(0.15, 0.05, 0.12),
                    probability=0.3,
                ),
                BranchOutcome(
                    id="tp-003-c",
                    label="Consolidate or Exit",
                    description="Merge with competitors or exit market due to margin compression.",
                    metric_delta=MetricSnapshot(-0.20, -0.15, 0.0),
                    probability=0.2,
                ),
            ],
        ),
    ]

    return Scenario(
        id="scenario-001",
        name="AI Leapfrog",
        description=(
            "A scenario where aggressive AI adoption reshapes the OTA landscape, "
            "rewarding early movers with proprietary AI capabilities while commoditizing "
            "traditional search-and-book intermediaries."
        ),
        timeline=timeline,
        nodes=nodes,
        strategic_profiles=profiles,
        competitors=competitors,
        metadata={
            "author": "Strategic Roadmap Engine",
            "version": "1.0",
            "base_year": "2025",
            "frameworks": "PESTEL, Porter's Five Forces, 2x2+S Matrix",
        },
    )


def save_scenarios(scenarios: List[Scenario], path: Optional[Path] = None) -> Path:
    """Serialize scenarios to JSON and write to disk."""
    output_path = path or (DATA_DIR / "scenarios.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = [asdict(s) for s in scenarios]
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return output_path


def load_scenarios(path: Optional[Path] = None) -> List[dict]:
    """Load scenarios from JSON file."""
    input_path = path or (DATA_DIR / "scenarios.json")
    return json.loads(input_path.read_text())


if __name__ == "__main__":
    scenario = build_sample_scenario()
    out = save_scenarios([scenario])
    print(f"Generated {out}")
