//@version=6
indicator("RS & MA Distance", overlay = false)

// === Display Helpers ===
table_pos       = position.bottom_left
size_tbl        = size.small
align_txt_left  = text.align_left
align_txt_right = text.align_right

// === Inputs: Lookback Periods ===
lookback_period_d = input.int(260, "52-Week Lookback (days)",  group = "Lookback")
lookback_period_w = input.int(52,  "52-Week Lookback (weeks)", group = "Lookback")

// === Inputs: RS Calculation ===
instrument_comparison = input.symbol("SPY", "Comparison Instrument",        group = "RS")
rs_lookback_length    = input.int(50,       "RS Look-back Length", minval=1, group = "RS")
rs_atr_length         = input.int(20,       "RS ATR Length",                group = "RS")

// === Inputs: ADR ===
adr_length_input = input.int(14, "ADR Length", group = "ADR")

// === Inputs: Nasdaq Overlay ===
nq_scale_daily    = input.int(90, "Nasdaq Scale (Daily)",    group = "Nasdaq")
nq_scale_intraday = input.int(9,  "Nasdaq Scale (Intraday)", group = "Nasdaq")
// Appended last so it doesn't shift any saved input positions. Multiplies
// (breadth_ratio - 1) up to roughly the same single-digit range rs lives in —
// see the S&P 500 Breadth Ratio block below for why that's a multiply now,
// not the divide the old New High/New Low line needed.
breadth_scale     = input.float(30, "Breadth Ratio Scale",   group = "Nasdaq")
// Buy/extreme thresholds on the RAW ratio (S5FI/S5TH), not the scaled plot —
// per Bang's own framework: ratio < 0.5 is a contrarian buy zone (short-term
// breadth washed out under an intact long-term trend), < 0.2 is extreme.
breadth_buy_ratio     = input.float(0.5, "Breadth Buy Threshold",     group = "Nasdaq")
breadth_extreme_ratio = input.float(0.2, "Breadth Extreme Threshold", group = "Nasdaq")

// === Inputs: Adaptive Color ===
// Used below to turn the fixed ±N-ADR thresholds on the 10MA/EMA21/50MA rows
// into per-stock ones, based on each stock's own typical ADR-distance rather
// than one number applied to every ticker regardless of how far it normally
// travels from its own MAs.
//
// Two-zone scheme: adr_red_mult x baseline is "full scale" (fully extended for
// this stock). adr_green_pct is what fraction of that counts as still a good
// entry — default 80%, so 0-80% of full scale reads green, beyond it reads
// red. No neutral zone in between by design; a stock is either within its
// normal entry range for its own typical extension, or past it.
adr_green_pct = input.float(0.8, "Adaptive Color: Green Zone (% of Full Scale)", minval=0.0, maxval=1.0, step=0.05, group="Adaptive Color")
adr_red_mult   = input.float(1.5, "Adaptive Color: Red Multiplier (Full Scale)", minval=0.1, step=0.1, group="Adaptive Color")
// Each MA row's baseline lookback is its OWN period x this multiplier, not one
// shared window — a 260-day lookback is ~26x the 10MA's own period but only
// ~5x the 50MA's, so the same window left the 10MA baseline much slower to
// reflect a change in the stock's behavior than the 50MA one, relative to what
// each row is actually measuring. Default 5x keeps the 50MA row close to its
// old fixed 260-day baseline while giving the 10MA/21MA rows a window
// proportional to their own, faster-moving period. Off-high is unaffected —
// it stays on lookback_period, since "52-week high" is a 52-week concept by
// definition already.
adr_baseline_mult = input.int(5, "Adaptive Baseline: Lookback (x MA period)", minval=1, group="Adaptive Color")

// === Inputs: Minute-Chart Day Stats ==========================================
// Appended last so no saved input position shifts. Drive the extra table that
// only exists on minute charts (see "Minute-Chart Day Stats Table" below).
stats_lookback_days = input.int(50,    "Lookback (completed daily bars)", minval=5, maxval=500, group="Minute Stats")
stats_move_thr1     = input.float(5.0,  "Move Threshold 1 (%)",  minval=0.1, step=0.5, group="Minute Stats")
stats_move_thr2     = input.float(10.0, "Move Threshold 2 (%)",  minval=0.1, step=0.5, group="Minute Stats")
stats_measure       = input.string("Daily range (High-Low)", "Move Measure", options=["Daily range (High-Low)", "Close-to-close change"], group="Minute Stats")

// === Inputs: Stage ===========================================================
// Same definitions as the "Swing: Stage" indicator (84 / 21 daily, 30 / 4 weekly).
// The 52-week window for the base-vs-top test reuses the Lookback inputs above
// (260 daily / 52 weekly). st_show switches the last table row on or off.
st_show        = input.bool(true, "Show Stage row (last row of table)", group = "Stage")
st_ma_len_d    = input.int(84,  "MA Length (Daily)",  minval = 2, group = "Stage")
st_ma_len_w    = input.int(30,  "MA Length (Weekly)", minval = 2, group = "Stage")
st_slope_len_d = input.int(21,  "Slope Lookback (Daily bars)",  minval = 1, group = "Stage")
st_slope_len_w = input.int(4,   "Slope Lookback (Weekly bars)", minval = 1, group = "Stage")
st_flat_thr_d  = input.float(0.30, "Flat Threshold, Daily (ADR)",  minval = 0.0, step = 0.05, group = "Stage")
st_flat_thr_w  = input.float(0.15, "Flat Threshold, Weekly (ADR)", minval = 0.0, step = 0.05, group = "Stage")
st_use_brk     = input.bool(true, "Early Stage 2 on Base Breakout", group = "Stage")
st_base_len_d  = input.int(125, "Base Length (Daily bars, ~6 months)",  minval = 10, group = "Stage")
st_base_len_w  = input.int(26,  "Base Length (Weekly bars, ~6 months)", minval = 5,  group = "Stage")
st_early_win_d = input.int(60,  "Early Window (Daily bars)",  minval = 5, group = "Stage")
st_early_win_w = input.int(12,  "Early Window (Weekly bars)", minval = 2, group = "Stage")
// How long the BUY / SELL tag stays on the cell, counted in bars INCLUDING the
// signal bar. 10 daily bars = two trading weeks, 2 weekly bars = the signal week
// plus the next.
st_sig_win_d   = input.int(10, "BUY / SELL Tag Window (Daily bars)",  minval = 1, group = "Stage")
st_sig_win_w   = input.int(2,  "BUY / SELL Tag Window (Weekly bars)", minval = 1, group = "Stage")

// Appended last so no saved input position shifts. Breadth dots turn red while the S&P 500
// is within this many percent of its 52-week high (see the S&P 500 Breadth Ratio block).
breadth_near_top_pct = input.float(5.0, "Breadth Dots Red When S&P 500 Within (% of 52-Week High)", minval = 0.0, step = 0.5, group = "Nasdaq")

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
len20 = timeframe.isweekly ?  4 : 21   // named to match len10/len50, used by ma20 below and by its adaptive baseline lookback

ma10 = ta.sma(close, len10)
ma20 = timeframe.isweekly ? ta.sma(close, len20) : ta.ema(close, len20)   // EMA21 on daily, SMA4 on weekly

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
// Removed: RS Slope and RS Acceleration (the linreg-slope / rate-of-change-of-
// slope pair that fed the "RS" table row's two numeric columns and their color
// logic) — the table row itself is gone, and nothing else read either value.
//
// Removed earlier: RS Pivot Structure (HH/HL on the RS line, plotted as the
// aqua "RS Structure Up" dot and the third RS table cell) and RS Bullish
// Divergence (teal dot on the zero line). Their calculations went with them —
// two ta.pivothigh/low calls, four persistent pivot vars, and two ta.lowest
// windows.

// =============================================================================
// === S&P 500 Breadth Ratio (% > 50MA / % > 200MA) ============================
// =============================================================================
// Placed, and plotted, before RS Plots and the Nasdaq Overlay below so it
// draws BEHIND both — Pine has no explicit z-index, draw order is purely
// call order, later plot()/fill() calls paint over earlier ones.
//
// S5FI / S5TH are TradingView's real percent-of-S&P-500-above-MA series (0-100
// range), not raw counts like the HIGQ/LOWQ pair this replaced. The ratio
// itself is centered on 1 (equal participation at both horizons), so it's
// plotted as (ratio - 1): zero means "no divergence between short- and
// long-term breadth," positive means more of the index is above its 50MA than
// its 200MA (short-term participation outrunning the long-term trend),
// negative the reverse (short-term breadth deteriorating under an intact
// long-term trend — often an early warning). (ratio - 1) is typically a small
// fraction, the opposite problem HIGQ-LOWQ had — so breadth_scale now
// multiplies it UP to sit in the same single-digit range rs lives in, instead
// of dividing a too-large number down.
//
// nq_hide is defined here, ahead of its other use in the Nasdaq Overlay
// section below, since this block needs it first now. Same guard, same
// reason in both places: S5FI/S5TH/IXIC are daily-resolution, so intraday
// they'd just be a flat step per session.
nq_hide = timeframe.isintraday or timeframe.isweekly

sp_above_50  = request.security("S5FI", "D", close)
sp_above_200 = request.security("S5TH", "D", close)
breadth_ratio = sp_above_200 != 0 ? sp_above_50 / sp_above_200 : float(na)

// Only the washed-out zone is drawn: ratio < breadth_buy_ratio means short-term breadth
// has dropped well below the long-term trend — a contrarian buy zone, brighter the lower
// it goes (bright below breadth_extreme_ratio, darker up to breadth_buy_ratio).
// Everywhere else the plot is na. Dots rather than a step line; size is editable in the
// Style tab.
//
// Colour = where the INDEX is, not just the breadth reading:
//   green - S&P 500 more than breadth_near_top_pct below its 52-week high: breadth is
//           washed out AND the index has already pulled back (the usual contrarian setup)
//   red   - S&P 500 within breadth_near_top_pct of its 52-week high: breadth is washed out
//           while the index is still near the top — weak participation under a strong
//           index, so the same dot is a warning rather than a buy zone
// The index's own daily bars are used (SPX, daily), so the distance does not depend on
// the stock on the chart. 52-week = lookback_period_d daily bars, the same window as the
// stock's "Off" row. Plotted on daily charts only (nq_hide), so the daily window is right.
spx_off_high_pct = request.security("SPX", "D", (ta.highest(high, lookback_period_d) - close) / ta.highest(high, lookback_period_d) * 100)
spx_near_top     = not na(spx_off_high_pct) and spx_off_high_pct < breadth_near_top_pct

breadth_in_zone = not na(breadth_ratio) and breadth_ratio < breadth_buy_ratio
breadth_extreme = breadth_ratio < breadth_extreme_ratio
breadth_color   = spx_near_top ? (breadth_extreme ? #ff4d4d : color.new(#c0392b, 30)) : (breadth_extreme ? #00ff7f : color.new(#2f9e4f, 30))

plot(nq_hide or not breadth_in_zone ? na : (breadth_ratio - 1) * breadth_scale, title="S&P 500 Breadth Ratio (50MA/200MA)", style=plot.style_circles, linewidth=2, color=breadth_color)

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
// (nq_hide itself is defined above, in the S&P 500 Breadth Ratio block — same
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

// Off 52-week high color — same adaptive approach as the MA-distance rows
// below: baseline is this stock's own lookback_period average of how far off
// its high it typically sits, in ADRs, so a name that normally trades 3 ADRs
// below its high needs a real breakdown to read red, not just its usual
// distance from a high it hasn't been near in a while. highest_high - close
// is never negative by construction, so there's no downside case to mirror
// here the way the MA rows need for below-MA readings.
adr_off_high = adr_ok ? (highest_high - close) / adr : float(na)

var float adr_off_high_run_sum = 0.0
var int   adr_off_high_run_n   = 0
if not na(adr_off_high)
    adr_off_high_run_sum += adr_off_high
    adr_off_high_run_n   += 1
adr_off_high_run_avg = adr_off_high_run_n > 0 ? adr_off_high_run_sum / adr_off_high_run_n : float(na)

adr_off_high_baseline_full = ta.sma(adr_off_high, lookback_period)
adr_off_high_baseline      = na(adr_off_high_baseline_full) ? adr_off_high_run_avg : adr_off_high_baseline_full

adr_off_high_full_scale = adr_off_high_baseline * adr_red_mult
pct_off_high_color      = na(adr_off_high_baseline) ? color.white : adr_off_high > adr_off_high_full_scale * adr_green_pct ? color.red : color.green

// 10MA distance colors — adaptive: baseline is this stock's own average of
// |v10adr| over len10 x adr_baseline_mult bars (its own MA period scaled up,
// not the shared 260-day lookback_period — see the Adaptive Baseline input),
// so a name that normally runs at 3 ADRs needs to clear a much higher bar
// than one that normally sits at 0.5 before it reads red. Falls back to a
// running average since inception while that window hasn't filled yet — same
// shape as running_high above, just a mean instead of a max, plus a not-na
// guard that one didn't need since v10adr can be na before adr_ok while high
// never is.
v10adr = adr_ok ? (close - ma10) / adr : float(na)

var float v10adr_run_sum = 0.0
var int   v10adr_run_n   = 0
if not na(v10adr)
    v10adr_run_sum += math.abs(v10adr)
    v10adr_run_n   += 1
v10adr_run_avg = v10adr_run_n > 0 ? v10adr_run_sum / v10adr_run_n : float(na)

v10adr_baseline_full = ta.sma(math.abs(v10adr), len10 * adr_baseline_mult)
v10adr_baseline      = na(v10adr_baseline_full) ? v10adr_run_avg : v10adr_baseline_full

v10adr_full_scale  = v10adr_baseline * adr_red_mult
v10adr_color       = na(v10adr_baseline) ? color.white : math.abs(v10adr) > v10adr_full_scale * adr_green_pct ? color.red : color.green
dist2_10ma_p_color = v10adr_color

// 20MA distance colors — same adaptive approach as 10MA above.
v20adr = adr_ok ? (close - ma20) / adr : float(na)

var float v20adr_run_sum = 0.0
var int   v20adr_run_n   = 0
if not na(v20adr)
    v20adr_run_sum += math.abs(v20adr)
    v20adr_run_n   += 1
v20adr_run_avg = v20adr_run_n > 0 ? v20adr_run_sum / v20adr_run_n : float(na)

v20adr_baseline_full = ta.sma(math.abs(v20adr), len20 * adr_baseline_mult)
v20adr_baseline      = na(v20adr_baseline_full) ? v20adr_run_avg : v20adr_baseline_full

v20adr_full_scale  = v20adr_baseline * adr_red_mult
v20adr_color       = na(v20adr_baseline) ? color.white : math.abs(v20adr) > v20adr_full_scale * adr_green_pct ? color.red : color.green
dist2_20ma_p_color = v20adr_color

// 50MA distance colors — same adaptive approach again. This also retires the
// old percent/ADR mismatch noted here previously (7 ADRs on a 5%-ADR name is
// ~35%, so a flat ±10% band and a flat ±7-ADR band could never agree by
// construction) — the percent cell now just mirrors the ADR cell's color
// directly, so there is nothing left for them to disagree about.
v50adr = adr_ok ? (close - ma50) / adr : float(na)

var float v50adr_run_sum = 0.0
var int   v50adr_run_n   = 0
if not na(v50adr)
    v50adr_run_sum += math.abs(v50adr)
    v50adr_run_n   += 1
v50adr_run_avg = v50adr_run_n > 0 ? v50adr_run_sum / v50adr_run_n : float(na)

v50adr_baseline_full = ta.sma(math.abs(v50adr), len50 * adr_baseline_mult)
v50adr_baseline      = na(v50adr_baseline_full) ? v50adr_run_avg : v50adr_baseline_full

v50adr_full_scale  = v50adr_baseline * adr_red_mult
v50adr_color       = na(v50adr_baseline) ? color.white : math.abs(v50adr) > v50adr_full_scale * adr_green_pct ? color.red : color.green
dist2_50ma_p_color = v50adr_color

// =============================================================================
// === Weinstein Stage (last table row) ========================================
// =============================================================================
// Same logic as the "Swing: Stage" indicator; see its header for the full reasoning.
// Replaces the old 1M / 3M / 6M RS % row (and its RS-ratio request).
//
//   LAYER 1 - slope stage. MA slope over the lookback, in ADR units (the ADR above),
//     against a flat band; price side decides the rest:
//       MA rising  + price above -> 2 Advancing     MA falling + price below -> 4 Declining
//       MA rising  + price below -> 3 Topping       MA falling + price above -> 1 Basing
//       MA flat                  -> 3 if the 52-week high is more recent than the low, else 1
//   LAYER 2 - base breakout. First close above the prior base_len-bar high, price above
//     the MA, MA not yet decisively rising -> called Stage 2 early ("2 Early") until the
//     slope takes over, a close falls back under the broken level, or the window runs out.
//   No volume test, by decision.
//
// Daily and weekly only: the stage MA is a 84-day / 30-week average, so on a minute or
// monthly chart the stage is na and the cell reads "n/a". There is no short-history
// fallback - a 10-bar "84MA" on a new IPO is not a stage MA.
//
// All ta.* run at global scope (ta.* inside barstate.islast returns na).
st_is_wk = timeframe.isweekly
st_tf_ok = timeframe.isdaily or timeframe.isweekly

st_ma_len    = st_is_wk ? st_ma_len_w    : st_ma_len_d
st_slope_len = st_is_wk ? st_slope_len_w : st_slope_len_d
st_flat_lim  = st_is_wk ? st_flat_thr_w  : st_flat_thr_d
st_base_len  = st_is_wk ? st_base_len_w  : st_base_len_d
st_early_win = st_is_wk ? st_early_win_w : st_early_win_d
st_sig_win   = st_is_wk ? st_sig_win_w   : st_sig_win_d

st_ma = ta.sma(close, st_ma_len)

// Slope in ADRs. adr_ok guards a zero ADR (halted names) against +/-inf.
st_slope = adr_ok ? (st_ma - st_ma[st_slope_len]) / adr : float(na)

// Offsets to the 52-week extremes: 0 = this bar, more negative = further back, so
// "greater" means "more recent". lookback_period is already 260 daily / 52 weekly.
st_hi_bar = ta.highestbars(high, lookback_period)
st_lo_bar = ta.lowestbars(low,  lookback_period)

st_above = close > st_ma

int st_slope_stage = na
if st_tf_ok and not na(st_slope)
    if st_slope > st_flat_lim
        st_slope_stage := st_above ? 2 : 3
    else if st_slope < -st_flat_lim
        st_slope_stage := st_above ? 1 : 4
    else if not na(st_hi_bar) and not na(st_lo_bar)
        st_slope_stage := st_hi_bar > st_lo_bar ? 3 : 1

// Resistance = highest high of the PRIOR base_len bars (the [1] stops a bar from being
// "above" a level it just set).
st_res    = ta.highest(high, st_base_len)[1]
st_broke  = close > st_res
st_pre_ok = not na(st_slope[1]) and st_slope[1] <= st_flat_lim

st_brk_event = st_use_brk and st_tf_ok and st_broke and not st_broke[1] and st_pre_ok and st_above

// The broken level is remembered while the breakout is still "early".
var float st_brk_level = na
var int   st_brk_bar   = na

if st_brk_event
    st_brk_level := st_res
    st_brk_bar   := bar_index
else if not na(st_brk_level)
    if close < st_brk_level or st_slope_stage == 2 or bar_index - st_brk_bar > st_early_win
        st_brk_level := na

st_early_only = not na(st_brk_level) and st_slope_stage != 2

int stage = st_slope_stage
if st_early_only
    stage := 2

// BUY / SELL tag. Same events as the red / green crosses in "Swing: Stage":
//   BUY  - the effective stage BECOMES 2 (a breakout lands here first; the later slope
//          hand-over does not re-fire, because the stage stays 2)
//   SELL - the effective stage LEAVES 2 (a failed early breakout counts)
// A single-bar event read only on the last bar would almost always be blank, so the tag
// is held for st_sig_win bars including the signal bar. The Stage text is always there;
// only the tag comes and goes.
st_enter2 = stage == 2 and not na(stage[1]) and stage[1] != 2
st_leave2 = stage[1] == 2 and not na(stage) and stage != 2

st_since_enter = ta.barssince(st_enter2)
st_since_leave = ta.barssince(st_leave2)

st_buy  = stage == 2 and not na(st_since_enter) and st_since_enter < st_sig_win
st_sell = not na(stage) and stage != 2 and not na(st_since_leave) and st_since_leave < st_sig_win

st_name = stage == 1 ? "1 Basing" : stage == 2 ? (st_early_only ? "2 Early" : "2 Advancing") : stage == 3 ? "3 Topping" : stage == 4 ? "4 Declining" : "n/a"
st_text = st_name + (st_buy ? "  ▲ BUY" : st_sell ? "  ▼ SELL" : "")

// Green = the only stage worth buying, yellow = caution, red = declining, white = basing / n/a.
st_color = stage == 2 ? color.green : stage == 3 ? color.yellow : stage == 4 ? color.red : color.white

// Sized to what is actually written: columns 1-4, five rows. (The original 6x22
// allocation was pure over-allocation, not a visual artifact — unset cells are
// not rendered, so those empty rows drew nothing.) The fifth row is the Stage row:
// label in column 1, the stage and its BUY / SELL tag in one merged cell over 2-4.
var data_table = table.new(position.top_right, 5, 5, bgcolor=color.new(color.black, 90), border_width=1, border_color=color.white)

// Table now renders on every timeframe, including minute charts. It previously
// carried `and not timeframe.isintraday`, which left the intraday pane showing
// only the RS line — the one part of this script with no intraday use — while
// hiding the MA-distance readout, which is the part that does.
if barstate.islast
    row_num = 0

    // --- Off 52-week High ---
    table.cell(data_table, 1, row_num, "Off", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, str.tostring(pct_off_high, "0.00") + "%", text_color=pct_off_high_color, text_size=size_tbl)
    table.cell(data_table, 3, row_num, na(adr_off_high_baseline) ? "N/A" : str.tostring(adr_off_high_baseline, "0.00"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 4, row_num, adr_ok ? str.tostring(adr_off_high, "0.00") : "N/A", text_color=pct_off_high_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to 10MA ---
    table.cell(data_table, 1, row_num, "10ma", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, str.tostring(dist2_10ma_p, "0.00") + "%", text_color=dist2_10ma_p_color, text_size=size_tbl)
    table.cell(data_table, 3, row_num, na(v10adr_baseline) ? "N/A" : str.tostring(v10adr_baseline, "0.00"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v10adr, "0.00"), text_color=v10adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to EMA21 (SMA4 on weekly) ---
    table.cell(data_table, 1, row_num, "21ma", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, str.tostring(dist2_20ma_p, "0.00") + "%", text_color=dist2_20ma_p_color, text_size=size_tbl)
    table.cell(data_table, 3, row_num, na(v20adr_baseline) ? "N/A" : str.tostring(v20adr_baseline, "0.00"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v20adr, "0.00"), text_color=v20adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // --- Distance to 50MA ---
    table.cell(data_table, 1, row_num, "50ma", text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 2, row_num, str.tostring(dist2_50ma_p, "0.00") + "%", text_color=dist2_50ma_p_color, text_size=size_tbl)
    table.cell(data_table, 3, row_num, na(v50adr_baseline) ? "N/A" : str.tostring(v50adr_baseline, "0.00"), text_color=color.white, text_size=size_tbl)
    table.cell(data_table, 4, row_num, str.tostring(v50adr, "0.00"), text_color=v50adr_color, text_size=size_tbl)
    row_num := row_num + 1

    // Uniform alignment: label column left, all three numeric columns right, so a
    // single column reads straight down. Previously set per row and inconsistently
    // — col 2 was right-aligned on the MA rows but default on the Off row, col 3
    // the reverse, and col 4 never aligned at all, leaving the numbers ragged.
    for r = 0 to 3
        table.cell_set_text_halign(data_table, 1, r, text_halign=align_txt_left)
        table.cell_set_text_halign(data_table, 2, r, text_halign=align_txt_right)
        table.cell_set_text_halign(data_table, 3, r, text_halign=align_txt_right)
        table.cell_set_text_halign(data_table, 4, r, text_halign=align_txt_right)

    // --- Stage: label in column 1, one merged cell across columns 2-4 ---
    // The row only exists when the switch is on. Cells 3 and 4 are created (empty) before
    // the merge so the merge has real cells to join, and alignment is passed to
    // table.cell itself because cell_set_text_halign errors on a cell never created.
    // The merged cell takes its text, colour and alignment from its top-left cell (col 2).
    if st_show
        table.cell(data_table, 1, row_num, "Stage", text_color=color.white, text_size=size_tbl, text_halign=align_txt_left)
        table.cell(data_table, 2, row_num, st_text, text_color=st_color, text_size=size_tbl, text_halign=align_txt_left)
        table.cell(data_table, 3, row_num, "", text_size=size_tbl)
        table.cell(data_table, 4, row_num, "", text_size=size_tbl)
        table.merge_cells(data_table, 2, row_num, 4, row_num)

// =============================================================================
// === Minute-Chart Day Stats Table ============================================
// =============================================================================
// Minute charts only. For the last `stats_lookback_days` COMPLETED daily bars:
//   - % of days whose move exceeded that day's own ADR%
//   - % of days whose move exceeded 2 x that day's own ADR%
//   - % of days whose move exceeded stats_move_thr1 (5%)
//   - % of days whose move exceeded stats_move_thr2 (10%)
//
// ADR% = daily ADR (SMA of high-low, the same ADR the rest of this script uses,
// at the daily length) / that day's close * 100, evaluated on each day itself —
// the reference moves with the stock's volatility through the window, it is not
// today's ADR% applied backwards. "Move" is the day's (high-low)/close*100 by
// default, so it is measured on the same basis as ADR%; the Move Measure input
// switches it to |close-to-close change| instead.
//
// Computed inside the daily request so no minute data is aggregated by hand. Window
// counts come from ta.sma over 0/1 flags (x length), not a dynamic [n] history
// offset, which Pine cannot size the buffer for inside a security context. Until
// n daily bars exist the sma is na, so a young ticker falls back to running totals
// (ta.cum) and reports over the days it has. Every value is lagged one daily bar
// and requested with lookahead_on — the standard non-repainting form — which also
// means the in-progress day is excluded: its range is still forming and would
// understate every row until the close.
f_day_stats(int n, float thr1, float thr2, int alen, bool c2c) =>
    adr_pct  = ta.sma(high - low, alen) / close * 100
    move_pct = c2c ? math.abs(close - close[1]) / close[1] * 100 : (high - low) / close * 100
    ok       = not na(adr_pct) and not na(move_pct) and adr_pct > 0

    f_valid = ok ? 1.0 : 0.0
    f_adr   = (ok and move_pct > adr_pct)     ? 1.0 : 0.0
    f_2adr  = (ok and move_pct > 2 * adr_pct) ? 1.0 : 0.0
    f_thr1  = (ok and move_pct > thr1)        ? 1.0 : 0.0
    f_thr2  = (ok and move_pct > thr2)        ? 1.0 : 0.0

    // All evaluated on every bar (ta.* must not sit inside a conditional branch).
    s_valid = ta.sma(f_valid, n)
    s_adr   = ta.sma(f_adr,   n)
    s_2adr  = ta.sma(f_2adr,  n)
    s_thr1  = ta.sma(f_thr1,  n)
    s_thr2  = ta.sma(f_thr2,  n)
    t_valid = ta.cum(f_valid)
    t_adr   = ta.cum(f_adr)
    t_2adr  = ta.cum(f_2adr)
    t_thr1  = ta.cum(f_thr1)
    t_thr2  = ta.cum(f_thr2)

    full    = not na(s_valid)
    w_valid = full ? math.round(s_valid * n) : t_valid
    w_adr   = full ? math.round(s_adr   * n) : t_adr
    w_2adr  = full ? math.round(s_2adr  * n) : t_2adr
    w_thr1  = full ? math.round(s_thr1  * n) : t_thr1
    w_thr2  = full ? math.round(s_thr2  * n) : t_thr2
    [w_valid[1], w_adr[1], w_2adr[1], w_thr1[1], w_thr2[1]]

[st_n, st_adr, st_2adr, st_thr1, st_thr2] = request.security(syminfo.tickerid, "D", f_day_stats(stats_lookback_days, stats_move_thr1, stats_move_thr2, adr_length_input, stats_measure == "Close-to-close change"), lookahead = barmerge.lookahead_on)

// Functions must be declared at global scope, so this sits outside the if below.
f_pct(float hits, float days) => (na(hits) or na(days) or days <= 0) ? "N/A" : str.tostring(hits / days * 100, "0") + "%"

// `na` on every other timeframe: an allocated table draws its frame even with no
// cells written, so it is only created where it is used.
var table stats_table = timeframe.isminutes ? table.new(table_pos, 2, 4, bgcolor=color.new(color.black, 90), border_width=1, border_color=color.white) : na

if barstate.islast and timeframe.isminutes
    table.cell(stats_table, 0, 0, "> ADR%", text_color=color.white, text_size=size_tbl)
    table.cell(stats_table, 1, 0, f_pct(st_adr, st_n), text_color=color.white, text_size=size_tbl)

    table.cell(stats_table, 0, 1, "> 2×ADR%", text_color=color.white, text_size=size_tbl)
    table.cell(stats_table, 1, 1, f_pct(st_2adr, st_n), text_color=color.white, text_size=size_tbl)

    table.cell(stats_table, 0, 2, "> " + str.tostring(stats_move_thr1, "#.##") + "%", text_color=color.white, text_size=size_tbl)
    table.cell(stats_table, 1, 2, f_pct(st_thr1, st_n), text_color=color.white, text_size=size_tbl)

    table.cell(stats_table, 0, 3, "> " + str.tostring(stats_move_thr2, "#.##") + "%", text_color=color.white, text_size=size_tbl)
    table.cell(stats_table, 1, 3, f_pct(st_thr2, st_n), text_color=color.white, text_size=size_tbl)

    for r = 0 to 3
        table.cell_set_text_halign(stats_table, 0, r, text_halign=align_txt_left)
        table.cell_set_text_halign(stats_table, 1, r, text_halign=align_txt_right)

// =============================================================================
// === Background: NDFD Market Condition =======================================
// =============================================================================
daily_close_ndfd = request.security("NDFD", "D", close)
color bg_color = na

// Daily only: on intraday (minute) charts the pane shows the tables and nothing
// else, so the NDFD tint is not drawn there.
if timeframe.isdaily
    if daily_close_ndfd < 10
        bg_color := color.new(color.green, 90)
    else if daily_close_ndfd > 85
        bg_color := color.new(color.red, 90)

bgcolor(bg_color)
