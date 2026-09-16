//@version=6
indicator("RS & MA Distance", overlay = false)

// === Display Helpers ===
table_pos       = position.bottom_right
size_tbl        = size.small
align_txt_left  = text.align_left
align_txt_right = text.align_right

// === Inputs: Lookback Periods ===
lookback_period_d = input.int(260, "52-Week Lookback (days)",  group = "Lookback")
lookback_period_w = input.int(52,  "52-Week Lookback (weeks)", group = "Lookback")
// Reserved: kept so saved indicator settings stay aligned. The MA-distance
// histogram it fed was removed (see note below) and nothing reads it today.
lookback_dist     = input.int(21,  "MA Distance Lookback",     group = "Lookback")

// === Inputs: RS Calculation ===
instrument_comparison = input.symbol("SPY", "Comparison Instrument",        group = "RS")
rs_lookback_length    = input.int(50,       "RS Look-back Length", minval=1, group = "RS")
rs_atr_length         = input.int(20,       "RS ATR Length",                group = "RS")
rs_avg_length         = input.int(10,       "(unused) RS Average Length",    group = "RS")
rs_consecutive_bars   = input.int(6,        "(unused) RS Consecutive Bars",  minval=2, group = "RS")
rs_accel_length       = input.int(5,        "RS Acceleration Length",        group = "RS")
rs_slope_length       = input.int(20,       "RS Slope Length",               group = "RS")
// Reserved: fed the removed RS Bullish Divergence. Kept declared because deleting
// a mid-list input shifts the saved values of every input after it — here that
// would silently move your ADR Length and Nasdaq scales onto the wrong slots.
rs_div_lookback       = input.int(20,       "(unused) RS Divergence Lookback", group = "RS")

// === Inputs: ADR ===
adr_length_input = input.int(14, "ADR Length", group = "ADR")

// === Inputs: Nasdaq Overlay ===
nq_scale_daily    = input.int(90, "Nasdaq Scale (Daily)",    group = "Nasdaq")
nq_scale_intraday = input.int(9,  "Nasdaq Scale (Intraday)", group = "Nasdaq")
// Appended last so it doesn't shift any saved input positions. Divides the
// HIGQ-LOWQ line down to roughly the same single-digit range rs lives in — see
// the New High/New Low block below for why that matters.
nhnl_scale        = input.int(10, "New High/Low Scale",      group = "Nasdaq")

// =============================================================================
// === Moving Averages =========================================================
// =============================================================================
// PERF: lengths are resolved first, then each ta.* runs exactly once at global
// scope. The old form assigned ma20/ma50/ma150 with ta.sma calls *inside*
// `if timeframe.isweekly`, which is the pattern that leaves ta.* state stale
// (and triggers CW10003) — and it instantiated both the daily and weekly series.
//
// ma150 / dist2_150ma / dist2_150ma_p were computed but never read anywhere in
// the script. Removing the 150-length SMA also drops the script's max_bars_back
// requirement from 150 to 50.
// BUGFIX: ma10 was never adjusted for weekly. Since len50 becomes 10 on weekly,
// ma10 = SMA(close, 10) and ma50 = SMA(close, 10) were THE SAME SERIES there —
// the "10MA" and "50MA" table rows showed identical numbers on every weekly
// chart. len10 now mirrors chart.pine (4 weeks ~ 10 days, 10 weeks ~ 50 days),
// which both removes the collision and makes the two panes agree on what "10MA"
// means.
len10 = timeframe.isweekly ?  4 : 10
len50 = timeframe.isweekly ? 10 : 50

ma10 = ta.sma(close, len10)
ma20 = timeframe.isweekly ? ta.sma(close, 4) : ta.ema(close, 21)   // EMA21 on daily, SMA4 on weekly

// Fallback: ta.sma yields na until its window fills, so on a recent IPO the
// 50MA is undefined for the first 49 bars and every 50MA cell reads NaN. Reuses
// the ma10 series already built above, so the fallback costs nothing extra.
ma50_full = ta.sma(close, len50)
ma50      = na(ma50_full) ? ma10 : ma50_full

// Distance from close to each MA (absolute and percentage)
dist2_10ma   = close - ma10
dist2_20ma   = close - ma20
dist2_50ma   = close - ma50

dist2_10ma_p = ma10 != 0 ? dist2_10ma / ma10 * 100 : float(na)
dist2_20ma_p = ma20 != 0 ? dist2_20ma / ma20 * 100 : float(na)
dist2_50ma_p = ma50 != 0 ? dist2_50ma / ma50 * 100 : float(na)

// === 52-Week High Proximity ===
// BUGFIX: ta.highest(high, 260) is na until 260 bars exist, and na > 3.0 is
// false — so on any stock with under ~13 months of history pct_off_high was na
// and the "Off" row read NaN.
//
// Fallback is a running high maintained since the first bar — the longest window
// the history actually supports. Done with a var rather than
// ta.highest(high, math.min(lookback_period, bar_index + 1)) because a series
// length there forces Pine to widen max_bars_back; this is O(1) and needs none.
lookback_period  = timeframe.isweekly ? lookback_period_w : lookback_period_d

var float running_high = na
running_high := na(running_high) ? high : math.max(running_high, high)

highest_high_full = ta.highest(high, lookback_period)
highest_high      = na(highest_high_full) ? running_high : highest_high_full

pct_off_high     = highest_high != 0 ? (highest_high - close) / highest_high * 100 : float(na)

// NOTE: the MA-distance histogram colour block that lived here
// (highest_dist / lowest_dist / dist_color) was dead — dist_color was assigned
// on every bar but never passed to a plot. It cost two rolling extremes over
// dist2_20ma_p plus the colour cascade. Removed.

// =============================================================================
// === Relative Strength (RS) ==================================================
// =============================================================================
// ADR vs ATR note:
//   ADR (Average Daily Range) = SMA of (high - low) — used for stock volatility scaling
//   ATR (Average True Range)  = includes gaps — used for RS normalization vs benchmark
//   They are intentionally different metrics for different purposes.

inst     = request.security(instrument_comparison, "", close)
inst_atr = request.security(instrument_comparison, "", ta.atr(rs_atr_length))

// PERF: the stock's own ATR was previously fetched via
// request.security(syminfo.tickerid, "", ta.atr(...)) — same symbol, same
// timeframe, so the request did nothing except consume one of the 40 available
// request slots (and is one of the cases that can hand back na). Called directly.
stock_atr = ta.atr(rs_atr_length)

// Benchmark and stock change, each normalized by their own ATR.
// Guarded against a zero ATR only — na stays na so the warm-up window behaves
// exactly as it did before.
bench_change_norm = inst_atr  > 0 ? (inst - inst[1])   / inst_atr  : float(na)
stock_change_norm = stock_atr > 0 ? (close - close[1]) / stock_atr : float(na)

// Cumulative ATR-normalized change over the lookback window
bench_cum_change = math.sum(bench_change_norm, rs_lookback_length)
stock_cum_change = math.sum(stock_change_norm, rs_lookback_length)

// RS = stock outperformance vs benchmark (positive = outperforming)
rs = stock_cum_change - bench_cum_change

// =============================================================================
// === RS Enhancements =========================================================
// =============================================================================

// --- 1. RS Slope (linear regression slope — direction and magnitude) ---
// Positive and growing = gaining strength; positive but flattening = stalling
rs_slope = ta.linreg(rs, rs_slope_length, 0) - ta.linreg(rs, rs_slope_length, 1)

// --- 2. RS Acceleration (rate-of-change of the slope) ---
// Positive = strength building; negative = fading even if slope still positive
rs_roc   = rs - rs[rs_accel_length]
rs_accel = rs_roc - rs_roc[rs_accel_length]

// Removed: RS Pivot Structure (HH/HL on the RS line, plotted as the aqua
// "RS Structure Up" dot and the third RS table cell) and RS Bullish Divergence
// (teal dot on the zero line). Their calculations went with them — two
// ta.pivothigh/low calls, four persistent pivot vars, and two ta.lowest windows.

// === RS table display values — all computed at global scope (Pine v6 safe) ===

// Slope: bright green when rising fast, dim green when rising slow, same logic for red
rs_slope_color  = rs_slope > 0.05 ? color.lime : rs_slope > 0 ? color.new(color.green, 40) : rs_slope < -0.05 ? color.rgb(255, 80, 80) : color.new(color.red, 40)

// Acceleration: green only when slope is also positive (real momentum); yellow when
// accelerating but slope still negative (early turn); red when losing speed
rs_accel_str    = rs_accel > 0 ? "ACC+" : rs_accel < 0 ? "ACC-" : "ACC~"
rs_accel_color  = rs_accel > 0 and rs_slope > 0 ? color.lime : rs_accel > 0 and rs_slope <= 0 ? color.yellow : rs_accel < 0 and rs_slope < 0 ? color.rgb(255, 80, 80) : rs_accel < 0 ? color.new(color.orange, 20) : color.gray

// =============================================================================
// === Nasdaq New High - New Low ===============================================
// =============================================================================
// Placed, and plotted, before RS Plots and the Nasdaq Overlay below so it
// draws BEHIND both — Pine has no explicit z-index, draw order is purely
// call order, later plot()/fill() calls paint over earlier ones.
//
// HIGQ / LOWQ are raw daily counts of Nasdaq stocks making a fresh 52-week
// high / low — typically tens to a few hundred, occasionally higher on
// breadth-thrust days. rs lives in single digits, so plotted directly this
// would dwarf the RS line exactly the way the raw IXIC MA spread does below —
// same problem, same fix: divide down by nhnl_scale so the line sits in a
// comparable range instead of blowing out the pane's scale.
//
// nq_hide is defined here, ahead of its other use in the Nasdaq Overlay
// section below, since this block needs it first now. Same guard, same
// reason in both places: HIGQ/LOWQ/IXIC are daily-resolution, so intraday
// they'd just be a flat step per session.
nq_hide = timeframe.isintraday or timeframe.isweekly

higq_close = request.security("HIGQ", "D", close)
lowq_close = request.security("LOWQ", "D", close)
nhnl_diff  = higq_close - lowq_close

// Blue/orange rather than green/red — this chart already uses green/red for
// the RS line, the Nasdaq fill, and the table, so a second series on the same
// two hues would blend into whichever one happens to agree with it that day.
nhnl_color = nhnl_diff >= 0 ? color.new(#3d8bfd, 75) : color.new(#ff9f43, 75)

plot(nq_hide ? na : nhnl_diff / nhnl_scale, title="Nasdaq New High - New Low", style=plot.style_stepline, color=nhnl_color)

// =============================================================================
// === RS Plots ================================================================
// =============================================================================
// RS visuals are suppressed on intraday, zero line included. The RS series is
// built from 50 bars of ATR-normalized change, so on a minute chart it measures
// relative strength over the last ~50 minutes against SPY — a horizon with no
// bearing on a swing thesis. On intraday this pane therefore carries the stats
// table and nothing else.
rs_hide = timeframe.isintraday

plot(rs_hide ? na : 0,      "ZERO LINE", color.new(color.white, 70))
plot(rs_hide ? na : rs,     "RS", rs > 0 ? color.green : color.red, linewidth=1)

// =============================================================================
// === Nasdaq Overlay ==========================================================
// =============================================================================
nasdaq_close = request.security("IXIC", "D", close)

nq_ma50 = ta.sma(nasdaq_close, 50)
nq_ma10 = ta.sma(nasdaq_close, 10) - nq_ma50   // offset from MA50 for scaled overlay
nq_ma20 = ta.ema(nasdaq_close, 21) - nq_ma50

nq_scale = timeframe.isminutes ? nq_scale_intraday : nq_scale_daily

// The overlay is only meaningful on daily. On intraday `nasdaq_close` comes from
// a "D" request, so it is a step function that updates once per session and the
// band sits dead flat; on weekly the fill was already set fully transparent.
//
// AUTOSCALE FIX: the two plots below are display.none, so they stay out of the
// scale — but `fill()` defaults to visible, and a visible fill claims vertical
// range even when its endpoints are hidden. With nq_scale_intraday at 9 against
// 90 on daily, and a numerator in absolute IXIC index points (a 10MA/50MA spread
// of 300-800 points at index 20,000), that invisible band spanned roughly ±35 to
// ±90 while rs lives in single digits — flattening the RS line into a trace.
// Feeding the plots na on those timeframes removes the range entirely; na
// contributes nothing to autoscale, and there was nothing visible to lose.
// (nq_hide itself is defined above, in the New High/New Low block — same
// condition, needed there first now.)

nq_p10 = plot(nq_hide ? na : nq_ma10 / nq_scale, color=#5d606b, display=display.none)
nq_p21 = plot(nq_hide ? na : nq_ma20 / nq_scale, color=#cfcfa6, display=display.none)

color nq_fill_color = na
if timeframe.isintraday or timeframe.isweekly
    nq_fill_color := color.new(color.black, 100)
else if nq_ma10 > nq_ma20
    nq_fill_color := #58c79c5d
else
    nq_fill_color := #fc8989

fill(nq_p10, nq_p21, color=nq_fill_color)

// =============================================================================
// === ADR (Average Daily Range) ===============================================
// =============================================================================
// Use a longer period on intraday timeframes to maintain comparable smoothing.
// PERF: the result used to be piped through
// request.security(syminfo.tickerid, timeframe.period, adr) — same symbol, same
// timeframe. That round-trip changed nothing and burned a request slot.
adr_length = (timeframe.isdaily or timeframe.isweekly) ? adr_length_input : int(2.2 * adr_length_input)
adr = ta.sma(high - low, adr_length)
adr_ok = not na(adr) and adr != 0

// =============================================================================
// === Data Table — colors and values computed at global scope (Pine v6 safe) ==
// =============================================================================

// Off 52-week high color
pct_off_high_color = pct_off_high < 10 ? color.green : pct_off_high < 15 ? color.white : pct_off_high < 20 ? color.yellow : color.red

// 10MA distance colors
v10adr             = adr_ok ? (close - ma10) / adr : float(na)
dist2_10ma_p_color = dist2_10ma_p > 3 or dist2_10ma_p < -3 ? color.red : dist2_10ma_p > 0 ? color.green : color.white
v10adr_color       = v10adr > 3 or v10adr < -3 ? color.red : v10adr > 1 ? color.green : color.white

// 20MA distance colors
v20adr             = adr_ok ? (close - ma20) / adr : float(na)
dist2_20ma_p_color = dist2_20ma_p > 4 or dist2_20ma_p < -4 ? color.red : dist2_20ma_p > 0 ? color.green : color.white
v20adr_color       = v20adr > 4 or v20adr < -4 ? color.red : v20adr > 1 ? color.green : color.white

// 50MA distance colors
// The percent cell was previously `> 0 ? green : red` — binary, with no extension
// tier. Under "red = far from entry" that called +40% above the 50MA green, and it
// contradicted v50adr_color in the same row, which does red out beyond ±7.
// ±10% continues the 3 → 4 → 10 progression of the rows above. Note this can
// never truly reconcile with the ADR cell: 7 ADRs on a 5%-ADR name is ~35%, so a
// flat percentage band and an ADR band disagree by construction.
v50adr             = adr_ok ? (close - ma50) / adr : float(na)
dist2_50ma_p_color = dist2_50ma_p > 10 or dist2_50ma_p < -10 ? color.red : dist2_50ma_p > 0 ? color.green : color.white
v50adr_color       = v50adr > 7 or v50adr < -7 ? color.red : v50adr > 1 ? color.green : color.white

// Sized to what is actually written: columns 1-4, five rows. (The original 6x22
// allocation was pure over-allocation, not a visual artifact — unset cells are
// not rendered, so those empty rows drew nothing.)
var data_table = table.new(position.top_right, 5, 5, bgcolor=color.new(color.black, 90), border_width=1, border_color=color.white)

// Table now renders on every timeframe, including minute charts. It previously
// carried `and not timeframe.isintraday`, which left the intraday pane showing
// only the RS line — the one part of this script with no intraday use — while
// hiding the MA-distance readout, which is the part that does.
if barstate.islast
    row_num = 0

    // --- Off 52-week High ---
    table.cell(data_table, 1, row_num, "Off", text_color=pct_off_high_color, text_size=size_tbl)
    table.cell(data_table, 2, row_num, close > 2 ? str.tostring(highest_high - close, "0.00") : str.tostring(highest_high, "0.0000"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 3, row_num, str.tostring(pct_off_high, "0.00") + "%", text_color=pct_off_high_color, text_size=size_tbl)
    table.cell(data_table, 4, row_num, adr_ok ? str.tostring((highest_high - close) / adr, "0.00") : "N/A", text_color=color.white, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to 10MA ---
    table.cell(data_table, 1, row_num, "10MA", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, close > 2 ? str.tostring(dist2_10ma, "0.00") : str.tostring(dist2_10ma, "0.0000"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 3, row_num, str.tostring(dist2_10ma_p, "0.00") + "%", text_color=dist2_10ma_p_color, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v10adr, "0.00"), text_color=v10adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to EMA21 (SMA4 on weekly) ---
    table.cell(data_table, 1, row_num, "EMA21", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, close > 2 ? str.tostring(dist2_20ma, "0.00") : str.tostring(dist2_20ma, "0.0000"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 3, row_num, str.tostring(dist2_20ma_p, "0.00") + "%", text_color=dist2_20ma_p_color, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v20adr, "0.00"), text_color=v20adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to 50MA ---
    table.cell(data_table, 1, row_num, "50MA", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, close > 2 ? str.tostring(dist2_50ma, "0.00") : str.tostring(dist2_50ma, "0.0000"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 3, row_num, str.tostring(dist2_50ma_p, "0.00") + "%", text_color=dist2_50ma_p_color, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v50adr, "0.00"), text_color=v50adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- RS Trend Row: slope / acceleration ---
    table.cell(data_table, 1, row_num, "RS", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, str.tostring(rs_slope, "0.00"), text_color=rs_slope_color, text_size=size_tbl)
    table.cell(data_table, 3, row_num, rs_accel_str, text_color=rs_accel_color, text_size=size_tbl)
    table.cell(data_table, 4, row_num, "", text_color=color.white, text_size=size_tbl)

    // Uniform alignment: label column left, all three numeric columns right, so a
    // single column reads straight down. Previously set per row and inconsistently
    // — col 2 was right-aligned on the MA rows but default on the Off row, col 3
    // the reverse, and col 4 never aligned at all, leaving the numbers ragged.
    // Applied after every cell exists; cell_set_text_halign on an uncreated cell
    // errors, which is why the RS row writes an empty col 4 above.
    for r = 0 to 4
        table.cell_set_text_halign(data_table, 1, r, text_halign=align_txt_left)
        table.cell_set_text_halign(data_table, 2, r, text_halign=align_txt_right)
        table.cell_set_text_halign(data_table, 3, r, text_halign=align_txt_right)
        table.cell_set_text_halign(data_table, 4, r, text_halign=align_txt_right)

// =============================================================================
// === Background: NDFD Market Condition =======================================
// =============================================================================
daily_close_ndfd = request.security("NDFD", "D", close)
color bg_color = na

if timeframe.isintraday or timeframe.isdaily
    if daily_close_ndfd < 10
        bg_color := color.new(color.green, 90)
    else if daily_close_ndfd > 85
        bg_color := color.new(color.red, 90)

bgcolor(bg_color)
