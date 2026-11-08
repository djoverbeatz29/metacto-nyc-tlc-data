"""NYC Yellow Taxi analytics dashboard — powered exclusively by dbt gold models.

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import data

st.set_page_config(page_title="NYC Yellow Taxi Analytics", page_icon="🚕", layout="wide")

PLOT_CFG = {"displaylogo": False}
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def money(x: float) -> str:
    return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"


def safe_div(a, b):
    return a / b if b else 0.0


# ---------------------------------------------------------------- load + filters
try:
    volume = data.trip_volume_hourly()
    zones = data.zone_revenue_daily()
    payments = data.payment_behavior_daily()
    dq = data.data_quality()
except KeyError as e:
    st.error(f"Missing Snowflake setting {e}. Copy .env.example to .env and fill it in.")
    st.stop()
except Exception as e:  # noqa: BLE001 — surface any connection/query error in the UI
    st.error(f"Could not load gold models from Snowflake: {e}\n\nHave you run `dbt build`?")
    st.stop()

min_d, max_d = volume["pickup_date"].min().date(), volume["pickup_date"].max().date()

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input("Pickup date range", (min_d, max_d), min_value=min_d, max_value=max_d)
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.info("Select a start and end date.")
        st.stop()
    start, end = (pd.Timestamp(d) for d in date_range)
    day_type = st.radio("Days", ["All days", "Weekdays", "Weekends"], horizontal=True)
    st.divider()
    refreshed = data.last_refreshed()
    st.caption(
        "Source: NYC TLC yellow taxi trip records · dbt gold layer on Snowflake."
        + (f"\n\nGold layer last built: {pd.Timestamp(refreshed):%Y-%m-%d %H:%M}" if refreshed is not None else "")
    )


def by_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df[(df["pickup_date"] >= start) & (df["pickup_date"] <= end)]
    if day_type != "All days":
        weekend = out["pickup_date"].dt.dayofweek >= 5
        out = out[weekend] if day_type == "Weekends" else out[~weekend]
    return out


v, z, p = by_date(volume), by_date(zones), by_date(payments)
if v.empty:
    st.warning("No trips in the selected range.")
    st.stop()

# ---------------------------------------------------------------- header + KPIs
st.title("🚕 NYC Yellow Taxi Analytics")
st.caption(f"{start:%b %d, %Y} – {end:%b %d, %Y} · {day_type.lower()} · valid trips only (see Data Quality)")

trips, revenue = v["trip_count"].sum(), v["total_revenue"].sum()
card = p[p["payment_type_name"] == "Credit card"]
k = st.columns(5)
k[0].metric("Trips", f"{trips:,.0f}")
k[1].metric("Revenue", money(revenue), help="Sum of total_amount (excludes cash tips)")
k[2].metric("Avg fare", money(safe_div(v["fare_revenue"].sum(), trips)))
k[3].metric("Avg distance", f"{safe_div(v['total_distance_miles'].sum(), trips):.2f} mi")
k[4].metric(
    "Card tip rate",
    f"{safe_div(card['tip_revenue'].sum(), card['fare_revenue'].sum()):.1%}",
    help="Tips / fare for credit-card trips. Cash tips are not recorded by TLC.",
)

tab_vol, tab_zone, tab_pay, tab_dq = st.tabs(
    ["📈 Trip volume", "📍 Pickup zones", "💳 Payment behavior", "🧪 Data quality"]
)

# ---------------------------------------------------------------- 1. trip volume
with tab_vol:
    c1, c2 = st.columns([1, 3])
    grain = c1.radio("Aggregation grain", ["Hour", "Day", "Week"], index=1, horizontal=True)
    measure = c2.radio("Measure", ["Trips", "Revenue"], horizontal=True)
    col = {"Trips": "trip_count", "Revenue": "total_revenue"}[measure]
    key = {"Hour": "pickup_hour", "Day": "pickup_date", "Week": "pickup_week"}[grain]

    series = v.groupby(key, as_index=False)[["trip_count", "total_revenue"]].sum()
    st.caption(
        f"Grain: one point per pickup **{grain.lower()}** (local NYC time), summed from the hourly gold mart."
        + (" Weeks start Monday; partial weeks at the edges of the range are smaller." if grain == "Week" else "")
    )
    fig = px.line(series, x=key, y=col, markers=grain != "Hour",
                  labels={key: "", col: measure})
    if grain != "Week" and len(series) > 2:
        # rolling average shows the trend under the daily/hourly noise
        window = 24 if grain == "Hour" else 7
        series["trend"] = series[col].rolling(window, min_periods=1, center=True).mean()
        fig.add_scatter(x=series[key], y=series["trend"], mode="lines", name=f"{window}-{grain.lower()} avg",
                        line={"dash": "dot", "width": 2})
    peak = series.loc[series[col].idxmax()]
    fig.add_annotation(x=peak[key], y=peak[col], text=f"Peak: {peak[col]:,.0f}", showarrow=True, arrowhead=2)
    fig.update_layout(height=380, margin={"t": 20, "b": 10}, legend={"orientation": "h", "y": 1.08})
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CFG)

    st.subheader("When is demand highest?")
    st.caption("Average trips per clock hour, by day of week. Darker = busier.")
    days = v.groupby("pickup_day_name")["pickup_date"].nunique()
    heat = v.groupby(["pickup_day_name", "pickup_hour_of_day"], as_index=False)["trip_count"].sum()
    heat["avg_trips"] = heat["trip_count"] / heat["pickup_day_name"].map(days)
    pivot = heat.pivot(index="pickup_day_name", columns="pickup_hour_of_day", values="avg_trips")
    pivot = pivot.reindex([d for d in DAY_ORDER if d in pivot.index])
    hm = px.imshow(pivot, aspect="auto", color_continuous_scale="Blues",
                   labels={"x": "Hour of day", "y": "", "color": "Avg trips"})
    hm.update_layout(height=320, margin={"t": 10, "b": 10})
    st.plotly_chart(hm, use_container_width=True, config=PLOT_CFG)

    busiest = heat.loc[heat["avg_trips"].idxmax()]
    st.info(
        f"Busiest slot: **{busiest['pickup_day_name']} {int(busiest['pickup_hour_of_day']):02d}:00**, "
        f"averaging **{busiest['avg_trips']:,.0f}** pickups in that hour."
    )

# ---------------------------------------------------------------- 2. pickup zones
with tab_zone:
    zone_tot = (
        z.groupby(["pickup_location_id", "pickup_zone_label", "pickup_zone", "pickup_borough", "is_airport",
                   "is_known_zone"], as_index=False)[["trip_count", "fare_revenue", "tip_revenue",
                                                     "total_revenue", "total_distance_miles"]].sum()
    )
    zone_tot["avg_fare"] = zone_tot["fare_revenue"] / zone_tot["trip_count"]
    zone_tot["revenue_per_trip"] = zone_tot["total_revenue"] / zone_tot["trip_count"]
    zone_tot["revenue_share"] = 100 * zone_tot["total_revenue"] / zone_tot["total_revenue"].sum()

    metrics = {
        "Total revenue": "total_revenue",
        "Trip count": "trip_count",
        "Average fare": "avg_fare",
        "Revenue per trip": "revenue_per_trip",
    }
    c1, c2, c3, c4 = st.columns([1.2, 1, 1.6, 1])
    metric_label = c1.selectbox("Rank zones by", list(metrics))
    top_n = c2.slider("Top N", 5, 40, 15)
    boroughs = sorted(zone_tot["pickup_borough"].dropna().unique())
    pick_boroughs = c3.multiselect("Boroughs", boroughs, default=[b for b in boroughs if b not in ("Unknown", "N/A")])
    min_trips = c4.number_input("Min trips", 0, value=100, step=50,
                                help="Hide low-volume zones so averages aren't driven by a handful of trips.")
    metric = metrics[metric_label]

    shown = zone_tot[zone_tot["pickup_borough"].isin(pick_boroughs) & (zone_tot["trip_count"] >= min_trips)]
    top = shown.nlargest(top_n, metric)
    bar = px.bar(top.sort_values(metric), x=metric, y="pickup_zone_label", orientation="h",
                 color="pickup_borough", labels={metric: metric_label, "pickup_zone_label": "",
                                                 "pickup_borough": "Borough"},
                 hover_data={"trip_count": ":,", "total_revenue": ":$,.0f", "avg_fare": ":$.2f"})
    bar.update_layout(height=max(350, 26 * len(top)), margin={"t": 10, "b": 10},
                      yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(bar, use_container_width=True, config=PLOT_CFG)

    if len(shown):
        top10_share = shown.nlargest(10, "total_revenue")["total_revenue"].sum() / shown["total_revenue"].sum()
        st.caption(f"The top 10 zones in this selection generate **{top10_share:.0%}** of its revenue.")

    st.dataframe(
        shown.sort_values(metric, ascending=False)[
            ["pickup_zone", "pickup_borough", "trip_count", "total_revenue", "avg_fare", "revenue_per_trip",
             "revenue_share"]],
        hide_index=True, use_container_width=True,
        column_config={
            "pickup_zone": "Zone", "pickup_borough": "Borough",
            "trip_count": st.column_config.NumberColumn("Trips", format="%d"),
            "total_revenue": st.column_config.NumberColumn("Revenue", format="$%.0f"),
            "avg_fare": st.column_config.NumberColumn("Avg fare", format="$%.2f"),
            "revenue_per_trip": st.column_config.NumberColumn("Revenue / trip", format="$%.2f"),
            "revenue_share": st.column_config.ProgressColumn("Share of revenue", format="%.2f%%",
                                                             min_value=0, max_value=float(shown["revenue_share"].max() or 1)),
        },
    )

# ---------------------------------------------------------------- 3. payment behavior
with tab_pay:
    pay = p.groupby("payment_type_name", as_index=False)[
        ["trip_count", "fare_revenue", "tip_revenue", "total_revenue", "total_distance_miles",
         "total_duration_minutes", "tipped_trip_count", "airport_trip_count"]].sum()
    pay = pay[pay["trip_count"] > 0]
    pay["share_of_trips"] = pay["trip_count"] / pay["trip_count"].sum()
    pay["avg_fare"] = pay["fare_revenue"] / pay["trip_count"]
    pay["avg_total"] = pay["total_revenue"] / pay["trip_count"]
    pay["avg_distance"] = pay["total_distance_miles"] / pay["trip_count"]
    pay["avg_duration"] = pay["total_duration_minutes"] / pay["trip_count"]
    pay["tip_rate"] = pay["tip_revenue"] / pay["fare_revenue"]
    pay["pct_tipped"] = pay["tipped_trip_count"] / pay["trip_count"]
    pay["airport_share"] = pay["airport_trip_count"] / pay["trip_count"]
    pay = pay.sort_values("trip_count", ascending=False)

    c1, c2 = st.columns(2)
    donut = px.pie(pay, names="payment_type_name", values="trip_count", hole=0.55, title="Share of trips")
    donut.update_layout(height=340, margin={"t": 40, "b": 0})
    c1.plotly_chart(donut, use_container_width=True, config=PLOT_CFG)

    compare = c2.selectbox("Compare payment types on",
                           {"Average fare": "avg_fare", "Average total charged": "avg_total",
                            "Average distance (mi)": "avg_distance", "Average duration (min)": "avg_duration",
                            "Share of airport trips": "airport_share"}.items(),
                           format_func=lambda kv: kv[0])
    cmp_bar = px.bar(pay, x="payment_type_name", y=compare[1], labels={compare[1]: compare[0],
                                                                         "payment_type_name": ""})
    cmp_bar.update_layout(height=290, margin={"t": 10, "b": 0})
    c2.plotly_chart(cmp_bar, use_container_width=True, config=PLOT_CFG)

    st.subheader("Does trip length change how people pay?")
    mix = p.groupby(["distance_band", "payment_type_name"], as_index=False)["trip_count"].sum()
    mix["share"] = mix["trip_count"] / mix.groupby("distance_band")["trip_count"].transform("sum")
    mix["distance_band"] = mix["distance_band"].str.split(": ").str[1]
    stack = px.bar(mix, x="distance_band", y="share", color="payment_type_name", barmode="stack",
                   labels={"distance_band": "Trip distance", "share": "Share of trips", "payment_type_name": "Payment"},
                   category_orders={"distance_band": ["< 1 mi", "1-3 mi", "3-7 mi", "7-15 mi", "15+ mi"]})
    stack.update_layout(height=340, margin={"t": 10, "b": 10}, yaxis_tickformat=".0%")
    st.plotly_chart(stack, use_container_width=True, config=PLOT_CFG)

    table = pay.copy()
    for c in ("share_of_trips", "pct_tipped", "tip_rate"):
        table[c] = 100 * table[c]
    st.dataframe(
        table[["payment_type_name", "trip_count", "share_of_trips", "avg_fare", "avg_distance", "avg_duration",
               "pct_tipped", "tip_rate"]],
        hide_index=True, use_container_width=True,
        column_config={
            "payment_type_name": "Payment type",
            "trip_count": st.column_config.NumberColumn("Trips", format="%d"),
            "share_of_trips": st.column_config.NumberColumn("Share", format="%.1f%%"),
            "avg_fare": st.column_config.NumberColumn("Avg fare", format="$%.2f"),
            "avg_distance": st.column_config.NumberColumn("Avg miles", format="%.2f"),
            "avg_duration": st.column_config.NumberColumn("Avg minutes", format="%.1f"),
            "pct_tipped": st.column_config.NumberColumn("% trips tipped", format="%.1f%%"),
            "tip_rate": st.column_config.NumberColumn("Tip / fare", format="%.1f%%"),
        },
    )
    st.caption("⚠️ TLC records card tips automatically but not cash tips, so cash trips show ~0% tips. "
               "Compare tipping only within card payments.")

# ---------------------------------------------------------------- 4. data quality
with tab_dq:
    st.caption("How raw TLC records become trusted trips. Every silver rule is a `dq_*` column in "
               "`silver.slv_trips_flagged`; this view reads `gold.agg_data_quality`. Not affected by the sidebar filters.")
    months = dq.groupby("source_month", as_index=False)[["total_rows", "valid_rows", "excluded_rows",
                                                          "total_amount_all_rows", "total_amount_valid_rows"]].first()
    tot = months[["total_rows", "valid_rows", "excluded_rows"]].sum()
    m = st.columns(4)
    m[0].metric("Raw rows", f"{tot.total_rows:,.0f}")
    m[1].metric("Valid trips", f"{tot.valid_rows:,.0f}")
    m[2].metric("Excluded", f"{tot.excluded_rows:,.0f}", f"{safe_div(tot.excluded_rows, tot.total_rows):.2%} of raw",
                delta_color="off")
    m[3].metric("Revenue excluded",
                money(months["total_amount_all_rows"].sum() - months["total_amount_valid_rows"].sum()))

    rules = dq.groupby("rule_name", as_index=False)[["rows_flagged", "rows_excluded_only_by_rule",
                                                     "total_amount_flagged"]].sum()
    rules = rules[rules["rows_flagged"] > 0].sort_values("rows_flagged")
    rules["rule"] = rules["rule_name"].str.replace("_", " ").str.capitalize()
    long = rules.melt(id_vars="rule", value_vars=["rows_flagged", "rows_excluded_only_by_rule"],
                      var_name="kind", value_name="rows")
    long["kind"] = long["kind"].map({"rows_flagged": "Rows flagged (overlapping)",
                                     "rows_excluded_only_by_rule": "Excluded by this rule alone"})
    dq_bar = px.bar(long, x="rows", y="rule", color="kind", barmode="group", orientation="h",
                    labels={"rows": "Rows", "rule": "", "kind": ""})
    dq_bar.update_layout(height=max(300, 45 * len(rules)), margin={"t": 10, "b": 10},
                         legend={"orientation": "h", "y": 1.1})
    st.plotly_chart(dq_bar, use_container_width=True, config=PLOT_CFG)
    st.caption("A row can break several rules. *Excluded by this rule alone* is each rule's unique impact: "
               "how many more trips you would keep if you dropped that rule.")
