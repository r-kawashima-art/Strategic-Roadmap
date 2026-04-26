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
    """A decision point where the scenario can branch.

    Phase 8 adds three optional provenance fields so the UI and the
    conversational `/expand` endpoint can tell apart hand-authored seed nodes
    from nodes minted in response to a user question:

    - ``source``: ``"seed"`` (authored in schema.py), ``"expansion"`` (added
      via `/expand`), or ``"revision"`` (added via `/revise`).
    - ``source_question``: the natural-language prompt that triggered an
      expansion (only meaningful when ``source == "expansion"``).
    - ``parent_branch_ids``: branch IDs that were rewired to flow into this
      node at expansion time — lets a reader see *why* the DAG points here.
    """

    id: str
    year: int
    title: str
    description: str
    external_driver: str  # e.g. "NDC adoption", "GenAI breakthrough"
    branches: List[BranchOutcome]
    source: str = "seed"
    source_question: Optional[str] = None
    parent_branch_ids: List[str] = field(default_factory=list)


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
            description=(
                "Volume-and-scale play: wins on commoditized hotel and flight "
                "inventory via performance marketing, aggressive cancellation "
                "flexibility, and operational efficiency. Typical of budget- "
                "focused brands (Agoda, eDreams), subscription-led price "
                "players, and flight-only aggregators."
            ),
            ai_adoption_bias=0.4,
            direct_booking_resilience=0.3,
            strategic_stance=StrategicStance.EFFICIENCY_LED,
        ),
        StrategicProfile(
            name="Differentiator",
            description=(
                "Content and experience play: invests in AI-driven "
                "personalization, premium UX (Trip Planner, AI concierges), "
                "unique inventory (Vrbo / homes), and brand. Defensible "
                "against airline direct-booking pressure because the value-add "
                "isn't just the ticket — it's itinerary, stay, and ancillary."
            ),
            ai_adoption_bias=0.9,
            direct_booking_resilience=0.7,
            strategic_stance=StrategicStance.INNOVATION_LED,
        ),
        StrategicProfile(
            name="Niche Search",
            description=(
                "Technical-moat play: solves a hard specialist problem "
                "airlines and hyperscalers can't easily copy — multi-city "
                "virtual interlining (Kiwi.com), complex multi-PNR "
                "itineraries, regional dominance. Volume is small but margin "
                "per booking and customer loyalty are high."
            ),
            ai_adoption_bias=0.7,
            direct_booking_resilience=0.5,
            strategic_stance=StrategicStance.INNOVATION_LED,
        ),
    ]

    # --- Competitor Profiles ---
    # initial_market_share values are normalized revenue-share proxies derived
    # from each firm's most recent public filings (see metadata.source /
    # source_year). Tracked OTAs sum to ~0.748; the remaining ~0.252 is folded
    # into the implicit "Other" bucket at projection time (Tripadvisor,
    # Despegar, Yatra, Webjet, Wego, LY.com, Tongcheng, MrJet, Skyscanner
    # referral revenue, and fragmented regional long-tail).
    #
    # Airbnb is tracked even though it's strictly a home-sharing marketplace —
    # it competes directly for lodging spend and its distribution decisions
    # shape the industry envelope around the modelled OTA cohort. MakeMyTrip
    # was added in Phase 8 to cover the Indian outbound market, which is the
    # fastest-growing regional OTA book globally (2023→2024 bookings +32%).
    competitors = [
        CompetitorProfile(
            name="Booking Holdings",
            key_capability=(
                "Global performance-marketing scale; multi-brand "
                "(Booking.com, Priceline, Kayak); AI trip-planner / "
                "Priceline Penny; genius loyalty programme."
            ),
            initial_position=MatrixPosition(0.50, 0.65, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.278,
            metadata={
                "source": "Booking Holdings FY2024 10-K (NASDAQ: BKNG, ~$23.7B revenue)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "23.7",
            },
        ),
        CompetitorProfile(
            name="Expedia Group",
            key_capability=(
                "Brand portfolio (Expedia, Hotels.com, Vrbo); Trip Planner "
                "AI; retail + B2B (Expedia Partner Solutions, ~20% of revenue)."
            ),
            initial_position=MatrixPosition(0.50, 0.65, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.160,
            metadata={
                "source": "Expedia Group FY2024 10-K (NASDAQ: EXPE, ~$13.7B revenue)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "13.7",
            },
        ),
        CompetitorProfile(
            name="Airbnb",
            key_capability=(
                "Home-sharing marketplace + experiences; high brand recall "
                "with under-35 segment; AI-powered trip-planning rollout 2025."
            ),
            initial_position=MatrixPosition(0.20, 0.70, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.130,
            metadata={
                "source": "Airbnb Inc. FY2024 10-K (NASDAQ: ABNB, ~$11.1B revenue)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "11.1",
            },
        ),
        CompetitorProfile(
            name="Trip.com Group",
            key_capability=(
                "APAC dominance (China/SEA); TripGenie AI assistant at scale; "
                "outbound China travel recovery tailwind; Skyscanner metasearch."
            ),
            initial_position=MatrixPosition(0.40, 0.75, StrategicStance.INNOVATION_LED),
            default_profile="Differentiator",
            initial_market_share=0.090,
            metadata={
                "source": "Trip.com Group FY2024 Annual Report (NASDAQ/HK: TCOM, ~$7.3B revenue, ¥53.4B)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "7.3",
            },
        ),
        CompetitorProfile(
            name="Agoda",
            key_capability=(
                "APAC accommodations specialist; aggressive pricing + "
                "mobile-first UX; AgodaGPT pilot launched 2023; part of "
                "Booking Holdings."
            ),
            initial_position=MatrixPosition(0.40, 0.60, StrategicStance.EFFICIENCY_LED),
            default_profile="Cost Leader",
            initial_market_share=0.045,
            metadata={
                "source": "Booking Holdings FY2024 10-K (Agoda segment, est. ~$3.8B)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "3.8",
            },
        ),
        CompetitorProfile(
            name="MakeMyTrip",
            key_capability=(
                "India's dominant OTA (MMT, Goibibo, redBus brands); "
                "outbound India travel tailwind; fast-growing B2B and "
                "corporate-travel book."
            ),
            initial_position=MatrixPosition(0.35, 0.50, StrategicStance.EFFICIENCY_LED),
            default_profile="Cost Leader",
            initial_market_share=0.010,
            metadata={
                "source": "MakeMyTrip FY2024 20-F (NASDAQ: MMYT, ~$782M revenue)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "0.78",
            },
        ),
        CompetitorProfile(
            name="eDreams ODIGEO",
            key_capability=(
                "Prime Subscription (6.7M+ members, ~55% of revenue); "
                "flights-first European metasearch lineage; AI-assisted "
                "personalization on Prime."
            ),
            initial_position=MatrixPosition(0.50, 0.55, StrategicStance.EFFICIENCY_LED),
            default_profile="Cost Leader",
            initial_market_share=0.020,
            metadata={
                "source": "eDreams ODIGEO FY2025 Annual Report (BME: EDR, ~€674M revenue)",
                "source_year": "2025",
                "revenue_proxy_usd_bn": "0.73",
            },
        ),
        CompetitorProfile(
            name="Etraveli Group",
            key_capability=(
                "Nordic flights-focused OTA + white-label flight search "
                "backend (powers Booking.com Flights); B2B2C flight "
                "distribution specialist."
            ),
            initial_position=MatrixPosition(0.45, 0.55, StrategicStance.EFFICIENCY_LED),
            default_profile="Niche Search",
            initial_market_share=0.005,
            metadata={
                "source": "Etraveli Group 2023 filings (CVC Capital portfolio, private)",
                "source_year": "2023",
                "revenue_proxy_usd_bn": "0.40",
            },
        ),
        CompetitorProfile(
            name="Kiwi.com",
            key_capability=(
                "Virtual Interlining — ML-generated multi-PNR itineraries "
                "across non-partner carriers (proprietary algorithm); "
                "high-margin long-tail multi-city routes."
            ),
            initial_position=MatrixPosition(0.30, 0.65, StrategicStance.INNOVATION_LED),
            default_profile="Niche Search",
            initial_market_share=0.010,
            metadata={
                "source": "Kiwi.com 2024 reported bookings (~$1.8B GMV, private; General Atlantic-backed)",
                "source_year": "2024",
                "revenue_proxy_usd_bn": "0.22",
            },
        ),
    ]

    # --- Timeline (key years 1990-2040) ---
    # revenue_index is a revenue-scale proxy (1990 = 1.0). Real-world anchors:
    #   2019 = pre-COVID peak (~$400B OTA gross bookings globally);
    #   2020 = COVID collapse (~-65 to -73% depending on segment);
    #   2023 = recovery above 2019 for sector leaders.
    # market_share is the OTA share of total travel bookings (online + offline).
    # tech_adoption_velocity is a 0-1 digital-maturity index of the OTA sector.
    timeline = [
        TimelineDataPoint(1990, MetricSnapshot(1.0, 0.02, 0.05), "OTA industry nascent (pre-web)"),
        TimelineDataPoint(1995, MetricSnapshot(1.5, 0.03, 0.10)),
        TimelineDataPoint(2000, MetricSnapshot(3.5, 0.12, 0.22), "Dot-com peak; first OTA IPOs"),
        TimelineDataPoint(2001, MetricSnapshot(2.8, 0.10, 0.22), "9/11 travel shock"),
        TimelineDataPoint(2005, MetricSnapshot(6.0, 0.22, 0.32), "Priceline acquires Booking.com"),
        TimelineDataPoint(2007, MetricSnapshot(8.5, 0.28, 0.38), "iPhone launch — mobile era begins"),
        TimelineDataPoint(2008, MetricSnapshot(7.2, 0.28, 0.40), "Global financial crisis"),
        TimelineDataPoint(2010, MetricSnapshot(8.5, 0.31, 0.45), "Mobile booking scales"),
        TimelineDataPoint(2011, MetricSnapshot(9.2, 0.33, 0.48), "Airbnb $1B valuation — home-sharing enters OTA airspace"),
        TimelineDataPoint(2015, MetricSnapshot(12.0, 0.36, 0.58), "Meta-search era; mobile majority of bookings"),
        TimelineDataPoint(2017, MetricSnapshot(14.0, 0.37, 0.62), "Google Flights / Hotel Ads push intensifies"),
        TimelineDataPoint(2019, MetricSnapshot(17.0, 0.38, 0.68), "Pre-pandemic peak (~$400B gross bookings)"),
        TimelineDataPoint(2020, MetricSnapshot(5.5, 0.32, 0.70), "COVID-19 collapse (-67%)"),
        TimelineDataPoint(2022, MetricSnapshot(14.5, 0.34, 0.72), "Recovery to pre-COVID volume for leaders"),
        TimelineDataPoint(2023, MetricSnapshot(18.0, 0.35, 0.74), "GenAI emergence; Expedia Trip Planner / TripGenie launch"),
        TimelineDataPoint(2024, MetricSnapshot(20.5, 0.36, 0.76), "Record year — BKNG $23.7B, EXPE $13.7B, ABNB $11.1B"),
        TimelineDataPoint(2025, MetricSnapshot(22.5, 0.36, 0.78), "NDC 21.3 mainstream; AI agent pilots; OpenAI Operator GA"),
        TimelineDataPoint(2028, MetricSnapshot(28.0, 0.38, 0.83)),
        TimelineDataPoint(2030, MetricSnapshot(33.0, 0.40, 0.86), "AI agents reshape booking"),
        TimelineDataPoint(2035, MetricSnapshot(45.0, 0.42, 0.91)),
        TimelineDataPoint(2040, MetricSnapshot(60.0, 0.45, 0.94), "Autonomous travel planning default"),
    ]

    # --- Turning Point Nodes ---
    nodes = [
        TurningPointNode(
            id="tp-001",
            year=2025,
            title="NDC + ONE Order Adoption",
            description=(
                "IATA NDC 21.3 and ONE Order go mainstream on major carriers "
                "(Lufthansa Group, British Airways, American, Singapore). "
                "Retailing shifts from GDS passive content to airline-controlled "
                "offer management. OTAs decide whether to build direct NDC "
                "pipelines — unlocking ancillary revenue (seats, bags, meals) "
                "at the cost of higher integration effort — or stay passive "
                "behind GDS aggregators and risk eroding content parity "
                "against airline.com."
            ),
            external_driver="NDC adoption",
            branches=[
                BranchOutcome(
                    id="tp-001-a",
                    label="Embrace NDC + ONE Order",
                    description=(
                        "Build direct NDC pipelines to the major carriers; "
                        "integrate airline Offer & Order management; capture "
                        "rich content and ancillary margin. Higher cost-to-serve "
                        "per booking, but a defensible content-parity moat."
                    ),
                    metric_delta=MetricSnapshot(0.05, 0.02, 0.10),
                    probability=0.70,
                    next_node_id="tp-002",
                ),
                BranchOutcome(
                    id="tp-001-b",
                    label="Stay GDS-first",
                    description=(
                        "Maintain Amadeus / Sabre / Travelport as the primary "
                        "channel; mitigate content gaps with aggregator "
                        "partnerships. Lower upfront cost; gradual content "
                        "parity erosion vs direct airline.com over 2–3 years."
                    ),
                    metric_delta=MetricSnapshot(-0.03, -0.04, 0.02),
                    probability=0.30,
                    next_node_id="tp-002",
                ),
            ],
        ),
        TurningPointNode(
            id="tp-002",
            year=2028,
            title="AI Agent Gateway Decision",
            description=(
                "Generative-AI-powered travel agents (OpenAI Operator, "
                "Anthropic computer-use, Perplexity Travel, Google Gemini "
                "Travel) move from pilot to consumer default. Whoever sits "
                "between the user and the inventory captures the consumer "
                "relationship — and the margin. OTAs decide whether to build "
                "the agent themselves, partner with a platform provider, or "
                "defer the bet and protect the legacy search-and-book funnel."
            ),
            external_driver="GenAI breakthrough",
            branches=[
                BranchOutcome(
                    id="tp-002-a",
                    label="Build Proprietary AI Concierge",
                    description=(
                        "Heavy R&D into in-house conversational booking "
                        "(successor generations of Expedia Trip Planner, "
                        "Trip.com TripGenie, Priceline Penny). Owns the "
                        "consumer surface; defensible moat if adoption lands."
                    ),
                    metric_delta=MetricSnapshot(0.12, 0.06, 0.15),
                    probability=0.30,
                    next_node_id="tp-003",
                ),
                BranchOutcome(
                    id="tp-002-b",
                    label="Partner with AI Gatekeepers",
                    description=(
                        "Integrate as the travel-fulfillment backend for "
                        "OpenAI / Anthropic / Google agents. Fast to market, "
                        "low R&D burn; gives up the consumer-facing surface "
                        "to whoever owns the assistant."
                    ),
                    metric_delta=MetricSnapshot(0.08, 0.03, 0.12),
                    probability=0.50,
                    next_node_id="tp-003",
                ),
                BranchOutcome(
                    id="tp-002-c",
                    label="Defer AI Investment",
                    description=(
                        "Double down on search-and-book UX and performance "
                        "marketing. Lowest short-term cost; highest risk of "
                        "being routed around once agents reach mainstream "
                        "adoption (2029–2031 central estimate)."
                    ),
                    metric_delta=MetricSnapshot(-0.02, -0.05, 0.03),
                    probability=0.20,
                    next_node_id="tp-003",
                ),
            ],
        ),
        TurningPointNode(
            id="tp-003",
            year=2032,
            title="Airline Direct-Booking Tipping Point",
            description=(
                "Airlines capture >50% of flight bookings directly on domestic "
                "routes — propelled by NDC, loyalty-program lock-in, and AI "
                "agents that now query airline.com directly. OTAs no longer "
                "'own' the flight transaction and must redefine the value "
                "proposition or consolidate."
            ),
            external_driver="Airline direct booking dominance",
            branches=[
                BranchOutcome(
                    id="tp-003-a",
                    label="Pivot to Complex Itineraries",
                    description=(
                        "Focus on multi-city, multi-modal (flight + rail + car "
                        "+ lodge), multi-PNR itineraries that airlines and their "
                        "AI agents cannot serve directly. Higher margin per "
                        "trip; smaller addressable market."
                    ),
                    metric_delta=MetricSnapshot(0.10, -0.02, 0.08),
                    probability=0.45,
                ),
                BranchOutcome(
                    id="tp-003-b",
                    label="Become AI-First Aggregator",
                    description=(
                        "Transform into a marketplace API layer that suppliers "
                        "plug into and consumer-facing AI agents query. Volume "
                        "play in a post-consumer-UX world; margin compresses "
                        "but scale is enormous."
                    ),
                    metric_delta=MetricSnapshot(0.15, 0.05, 0.12),
                    probability=0.35,
                ),
                BranchOutcome(
                    id="tp-003-c",
                    label="Consolidate or Exit",
                    description=(
                        "M&A to gain scale, sell to a hyperscaler, or exit the "
                        "market as unit economics compress beyond viable "
                        "return on ad spend."
                    ),
                    metric_delta=MetricSnapshot(-0.20, -0.15, 0.0),
                    probability=0.20,
                ),
            ],
        ),
    ]

    return Scenario(
        id="scenario-001",
        name="AI Leapfrog",
        description=(
            "A scenario where NDC-driven retailing, Generative-AI travel "
            "agents, and airline direct-booking pressure compound over "
            "2025–2040. Early movers that build or partner into AI "
            "concierges capture the consumer surface; laggards on traditional "
            "search-and-book UX commoditize. Airline direct booking crosses "
            "50% by 2032, forcing OTAs to pivot to complex itineraries, "
            "become AI-first aggregators, or consolidate out."
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
