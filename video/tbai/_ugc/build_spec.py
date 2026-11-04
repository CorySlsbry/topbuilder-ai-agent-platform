import json
from pathlib import Path

CLIPS = Path(r"C:\Users\you\.geo-flywheel\broll\clips\top-builder-ai")
GOOGLE = str(CLIPS / "problem-serp-google-20260818-111414.mp4")
BING = str(CLIPS / "problem-serp-bing-20260818-111338.mp4")
BLOG = str(CLIPS / "site-blog-comparison-20260818-111535.mp4")
# site-home-scroll is EXCLUDED: frame-checked and found to carry a visible "$349/mo ... $499"
# pricing banner and a "$0 cancellation fee" line for nearly its whole 8s duration -- a hard
# violation of the no-price-on-screen rule. problem-serp-google is usable ONLY in its first
# ~4.5s (it later hits a real Google "unusual traffic" reCAPTCHA block page, unusable).
# problem-serp-bing is usable in [0, ~6s] and [~14.5, 18.2s] (the middle holds a YouTube
# thumbnail reading "$3,864" / "$150" / "$2,220" -- also a price). site-blog-comparison was
# frame-checked clean across its full 9.27s (blog prose + our own real long-form thumbnail).

def shot(src=None, in_=0.0, weight=1.0, caption=None):
    s = {"weight": weight}
    if src is not None:
        s["src"] = src
        s["in"] = in_
    if caption is not None:
        s["caption"] = caption
    return s

spec = {
    "lane": "top-builder-ai",
    "cluster": "real-time-job-cost-servicetitan",
    "source_id": "f935069d3c46c07a",
    "beats": [
        {
            "name": "hook",
            "visual": "avatar",
            "vo": "If you run ServiceTitan and can't say what last month's biggest job actually made, this is for you.",
            "shots": [
                shot(weight=1.2, caption={"mega": "STILL GUESSING?"}),
                shot(weight=1.0),
                shot(weight=1.0),
            ],
        },
        {
            "name": "problem",
            "visual": "broll",
            "vo": "ServiceTitan's own real time budget table only exists inside Project Management, built for commercial and construction work.",
            "shots": [
                shot(BLOG, 0.1, caption={"setup": "ServiceTitan's own", "payoff": "real time table"}),
                shot(GOOGLE, 0.2, caption={"setup": "only exists inside", "payoff": "Project Management"}),
                shot(BLOG, 0.9, caption={"setup": "built for", "payoff": "commercial work"}),
                shot(GOOGLE, 1.3, caption={"setup": "and", "payoff": "construction only"}),
            ],
        },
        {
            "name": "agitation",
            "visual": "broll",
            "vo": "Most residential and light commercial shops never see it. And even when it's on, the numbers move only after a bill posts, not while your crew's still on site.",
            "shots": [
                shot(BING, 0.2, caption={"setup": "Most shops", "payoff": "never see it"}),
                shot(BLOG, 1.7, caption={"setup": "The table's", "payoff": "turned off"}),
                shot(BING, 1.1, caption={"setup": "Even when it's on", "payoff": "it's not live"}),
                shot(GOOGLE, 2.4, caption={"setup": "Numbers move", "payoff": "after the bill"}),
                shot(BING, 2.0, caption={"setup": "Not while", "payoff": "you're mid-job"}),
                shot(BLOG, 2.5, caption={"setup": "Not while", "payoff": "crew's on site"}),
            ],
        },
        {
            "name": "mechanism",
            "visual": "broll",
            "vo": "Top Builder AI reads your committed and actual ServiceTitan costs every day, compares them to schedule progress, and flags a job the moment it drifts.",
            "shots": [
                shot(BLOG, 3.3, caption={"setup": "Top Builder AI", "payoff": "reads your costs"}),
                shot(BING, 2.9, caption={"setup": "committed and actual", "payoff": "side by side"}),
                shot(BLOG, 4.1, caption={"setup": "compares it to", "payoff": "schedule progress"}),
                shot(BING, 3.8, caption={"setup": "and flags", "payoff": "a job that drifts"}),
                shot(BLOG, 4.9, caption={"setup": "before", "payoff": "it's too late"}),
            ],
        },
        {
            "name": "proof",
            "visual": "broll",
            "vo": "No invented numbers, no edited records, just your real ServiceTitan and payroll data, built by a construction bookkeeper who does this for real trade shops.",
            "shots": [
                shot(BING, 15.0, caption={"setup": "No invented", "payoff": "numbers"}),
                shot(BLOG, 5.7, caption={"setup": "No edited", "payoff": "records"}),
                shot(BING, 16.0, caption={"setup": "Just your real", "payoff": "ServiceTitan data"}),
                shot(BLOG, 6.5, caption={"setup": "Built by a", "payoff": "construction bookkeeper"}),
                shot(BING, 16.8, caption={"setup": "For real", "payoff": "trade shops"}),
            ],
        },
        {
            "name": "cta",
            "visual": "avatar",
            "vo": "See exactly how it works against your own numbers. The breakdown's linked below.",
            "shots": [
                shot(weight=1.0, caption={"setup": "See exactly", "payoff": "how it works"}),
                shot(weight=1.0, caption={"setup": "Link's", "payoff": "below"}),
            ],
        },
    ],
}

out = Path(__file__).parent / "spec.json"
out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
print(f"wrote {out}")
