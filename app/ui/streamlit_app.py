import ast
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine


DB_URL = os.getenv("RENT_RADAR_DB_URL", "sqlite:////data/rent_radar.sqlite")

st.set_page_config(
    page_title="Rent Radar",
    layout="wide",
)

st.title("Rent Radar")
st.caption("Daily rental apartment intelligence dashboard")

engine = create_engine(DB_URL)


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql(query, engine, params=params)


def safe_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []

    return []


def safe_json(value):
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            return ast.literal_eval(value)
        except Exception:
            return {}

    return {}


def latest_snapshot_date():
    df = read_sql(
        """
        SELECT MAX(snapshot_date) AS snapshot_date
        FROM curated_listings
        """
    )

    if df.empty or pd.isna(df.loc[0, "snapshot_date"]):
        return None

    return df.loc[0, "snapshot_date"]


snapshot_date = latest_snapshot_date()

if not snapshot_date:
    st.warning("No curated listings found yet. Run the daily ingestion job first.")
    st.stop()


mode = st.sidebar.radio(
    "View",
    [
        "Top recommendations",
        "Gallery browser",
        "Full daily DB",
        "DQ issues",
        "Trends",
        "Lifecycle",
        "Source summary",
        "Orchestration",
    ],
)

st.sidebar.write(f"Snapshot: `{snapshot_date}`")


base_query = """
SELECT *
FROM curated_listings
WHERE snapshot_date = :snapshot_date
"""


df = read_sql(base_query, {"snapshot_date": snapshot_date})

if df.empty:
    st.warning("No listings for latest snapshot.")
    st.stop()


# Basic metrics
valid_df = df[
    (df["dq_is_category_page"] == 0)
    & (df["dq_price_suspicious"] == 0)
].copy()

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Daily rows", len(df))
col2.metric("Valid listings", len(valid_df))
col3.metric("Sources", df["source"].nunique())
col4.metric("Avg price", f"€{valid_df['price_eur_clean'].mean():.0f}" if not valid_df.empty else "n/a")
col5.metric("Avg €/m²", f"€{valid_df['price_per_m2'].mean():.2f}" if not valid_df.empty else "n/a")


if mode == "Top recommendations":
    st.subheader("Market snapshot")

    trend_df = read_sql(
        """
        SELECT *
        FROM listing_price_history
        ORDER BY snapshot_date
        """
    )

    life_df = read_sql(
        """
        SELECT *
        FROM listing_lifecycle
        """
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Recommendations", len(top))
    c2.metric("Avg top price", f"€{top['price_eur_clean'].mean():.0f}" if not top.empty else "n/a")
    c3.metric("Tracked listings", len(life_df) if not life_df.empty else 0)
    c4.metric(
        "Disappeared",
        len(life_df[life_df["current_status"] == "disappeared"]) if not life_df.empty else 0,
    )

    if not trend_df.empty and trend_df["snapshot_date"].nunique() > 1:
    daily_trend = (
        trend_df.groupby("snapshot_date")
        .agg(
            median_price=("price_eur", "median"),
            median_price_per_m2=("price_per_m2", "median"),
            listings=("id", "count"),
        )
        .reset_index()
    )

    with st.expander("Recent market trend"):
        st.line_chart(daily_trend.set_index("snapshot_date")[["median_price", "median_price_per_m2"]])

    st.subheader("Top picks")

    top = valid_df.sort_values("worth_checking_score", ascending=False).head(50)

    source_filter = st.multiselect(
        "Source",
        sorted(top["source"].dropna().unique()),
        default=sorted(top["source"].dropna().unique()),
    )

    if source_filter:
        top = top[top["source"].isin(source_filter)]

    for _, row in top.head(30).iterrows():
        with st.container(border=True):
            left, right = st.columns([2, 3])

            with left:
                image_paths = safe_list(row.get("local_image_paths"))
                if image_paths:
                    gallery_key = f"gallery_{row.get('id')}"
                    selected_idx = st.selectbox(
                        "Gallery",
                        list(range(len(image_paths))),
                        format_func=lambda i: f"Image {i + 1}/{len(image_paths)}",
                        key=gallery_key,
                    )
                    st.image(image_paths[selected_idx], use_column_width=True)
                else:
                    st.info("No saved images yet")

            with right:
                st.markdown(f"### {row.get('title') or 'Untitled listing'}")
                st.write(
                    f"**€{row.get('price_eur_clean')}** | "
                    f"{row.get('rooms')} camere | "
                    f"{row.get('surface_m2')} m² | "
                    f"{row.get('zone') or 'Unknown zone'} | "
                    f"Score: **{row.get('worth_checking_score')}**"
                )

                score_reasons = row.get("score_reasons")

                if score_reasons:
                    st.write("Why this was recommended:")
                    st.json(score_reasons)

                score_reasons = safe_json(row.get("score_reasons"))
                if score_reasons:
                    with st.expander("Why this was recommended"):
                        st.json(score_reasons)

                tags = []

                if row.get("is_pet_friendly"):
                    tags.append("pet friendly")

                if row.get("is_private_owner"):
                    tags.append("private owner")

                if row.get("has_no_commission"):
                    tags.append("no commission")

                if row.get("has_parking"):
                    tags.append("parking")

                if row.get("dq_price_suspicious"):
                    tags.append("price suspicious")

                if tags:
                    st.write("Tags: " + ", ".join(tags))

                st.write(f"Source: `{row.get('source')}`")
                st.link_button("Open listing", row.get("source_url"))


elif mode == "Full daily DB":
    st.subheader("Full daily DB")

    st.dataframe(
        df[
            [
                "snapshot_date",
                "source",
                "title",
                "zone",
                "rooms",
                "surface_m2",
                "price_eur_raw",
                "price_eur_clean",
                "price_per_m2",
                "worth_checking_score",
                "is_pet_friendly",
                "is_private_owner",
                "has_no_commission",
                "has_parking",
                "dq_price_suspicious",
                "dq_is_category_page",
                "source_url",
            ]
        ].sort_values("worth_checking_score", ascending=False),
        use_container_width=True,
        height=700,
    )


elif mode == "DQ issues":
    st.subheader("Data quality issues")

    dq = df[
        (df["dq_price_suspicious"] == 1)
        | (df["dq_missing_description"] == 1)
        | (df["dq_missing_images"] == 1)
        | (df["dq_is_category_page"] == 1)
    ].copy()

    st.write(f"DQ rows: {len(dq)}")

    st.dataframe(
        dq[
            [
                "source",
                "title",
                "zone",
                "rooms",
                "surface_m2",
                "price_eur_raw",
                "price_eur_clean",
                "dq_price_suspicious",
                "dq_missing_description",
                "dq_missing_images",
                "dq_is_category_page",
                "source_url",
            ]
        ],
        use_container_width=True,
        height=700,
    )


elif mode == "Trends":
    st.subheader("Trends")

    hist = read_sql(
        """
        SELECT *
        FROM listing_price_history
        ORDER BY snapshot_date
        """
    )

    if hist.empty:
        st.warning("No price history yet.")
        st.stop()

    daily = (
        hist.groupby("snapshot_date")
        .agg(
            listings=("id", "count"),
            avg_price=("price_eur", "mean"),
            median_price=("price_eur", "median"),
            avg_price_per_m2=("price_per_m2", "mean"),
            median_price_per_m2=("price_per_m2", "median"),
        )
        .reset_index()
    )

    st.write("Daily market overview")
    st.dataframe(daily, use_container_width=True)

    st.line_chart(daily.set_index("snapshot_date")[["avg_price", "median_price"]])
    st.line_chart(daily.set_index("snapshot_date")[["avg_price_per_m2", "median_price_per_m2"]])

    zone = st.selectbox(
        "Zone",
        ["All"] + sorted([z for z in hist["zone"].dropna().unique()]),
    )

    zone_hist = hist.copy()
    if zone != "All":
        zone_hist = zone_hist[zone_hist["zone"] == zone]

    by_zone = (
        zone_hist.groupby(["snapshot_date", "zone"])
        .agg(
            listings=("id", "count"),
            median_price=("price_eur", "median"),
            median_price_per_m2=("price_per_m2", "median"),
        )
        .reset_index()
    )

    st.write("Zone trend")
    st.dataframe(by_zone, use_container_width=True)


elif mode == "Lifecycle":
    st.subheader("Listing lifecycle")

    lifecycle = read_sql(
        """
        SELECT *
        FROM listing_lifecycle
        ORDER BY current_status, last_seen_date DESC
        """
    )

    if lifecycle.empty:
        st.warning("No lifecycle data yet.")
        st.stop()

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Tracked listings", len(lifecycle))
    col_b.metric("Active", len(lifecycle[lifecycle["current_status"] == "active"]))
    col_c.metric("Disappeared", len(lifecycle[lifecycle["current_status"] == "disappeared"]))

    st.dataframe(
        lifecycle[
            [
                "canonical_id",
                "current_status",
                "first_seen_date",
                "last_seen_date",
                "disappeared_date",
                "reappeared_date",
                "days_seen",
                "days_missing",
                "source_urls",
            ]
        ],
        use_container_width=True,
        height=700,
    )


elif mode == "Source summary":
    st.subheader("Source summary")

    source_summary = (
        df.groupby("source")
        .agg(
            rows=("id", "count"),
            valid_rows=("dq_is_category_page", lambda x: int((x == 0).sum())),
            avg_price=("price_eur_clean", "mean"),
            median_price=("price_eur_clean", "median"),
            avg_score=("worth_checking_score", "mean"),
        )
        .reset_index()
    )

    st.dataframe(source_summary, use_container_width=True)

    st.subheader("Zone summary")

    zone_summary = (
        valid_df.groupby("zone", dropna=False)
        .agg(
            listings=("id", "count"),
            avg_price=("price_eur_clean", "mean"),
            median_price=("price_eur_clean", "median"),
            avg_price_per_m2=("price_per_m2", "mean"),
            median_price_per_m2=("price_per_m2", "median"),
            avg_score=("worth_checking_score", "mean"),
        )
        .reset_index()
        .sort_values("listings", ascending=False)
    )

    st.dataframe(zone_summary, use_container_width=True)

elif mode == "Gallery browser":
    st.subheader("Gallery browser")

    gallery_df = valid_df[
        valid_df["local_image_paths"].notna()
    ].sort_values("worth_checking_score", ascending=False)

    for _, row in gallery_df.head(100).iterrows():
        image_paths = safe_list(row.get("local_image_paths"))

        if not image_paths:
            continue

        with st.container(border=True):
            st.markdown(f"### {row.get('title')}")
            st.write(
                f"€{row.get('price_eur_clean')} | "
                f"{row.get('zone')} | "
                f"{row.get('rooms')} camere | "
                f"{row.get('surface_m2')} m²"
            )

            cols = st.columns(min(4, len(image_paths)))
            for idx, path in enumerate(image_paths[:8]):
                with cols[idx % len(cols)]:
                    st.image(path, use_column_width=True)

            st.link_button("Open listing", row.get("source_url"))

elif mode == "Orchestration":
    st.subheader("Pipeline runs")

    try:
        runs = read_sql(
            """
            SELECT *
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 100
            """
        )
        st.dataframe(runs)
    except Exception as exc:
        st.info(f"No pipeline_runs table yet or no runs recorded: {exc}")

    st.subheader("Crontab")

    st.code(
        "On Pi:\n"
        "0 4 * * * cd /home/pi/homelab/rent-radar && "
        "docker compose -f docker-compose.prod.yml --profile manual run --rm rent-radar-daily "
        ">> /home/pi/homelab/rent-radar/logs/cron.log 2>&1"
    )

    st.subheader("Recent cron log")

    cron_path = "/logs/cron.log"
    try:
        with open(cron_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-120:]
        st.text("".join(lines))
    except Exception:
        st.info("No cron log found yet.")