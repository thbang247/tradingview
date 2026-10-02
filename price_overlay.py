//@version=6
indicator("Charts", "", true)

// ----------------------------------------------------------------------------------------------------------------------------------
// Chart
// ----------------------------------------------------------------------------------------------------------------------------------
// === Inputs: MA Visibility ===
MA10              = input.bool(false, "MA 10",           group = "Price")
MA21              = input.bool(false, "EMA 21",          group = "Price")
MA50              = input.bool(true,  "MA 50",           group = "Price")
MA150             = input.bool(false, "MA 150",          group = "Price")
MA200             = input.bool(false, "MA 200",          group = "Price")
ema21_bands_input = input.bool(false, "EMA 21 Bands",   group = "Price")

// === Inputs: ADR ===
adr_length_input = input.int(14, "ADR Length", group = "Action")

// === Inputs: Earnings & Sales ===
show_earnings_table   = input.bool(true, "Show Earnings & Sales Table", group = "Earnings & Sales")
earnings_growth_thresh = input.float(30, "Good Growth Threshold (%)",  group = "Earnings & Sales")

isStock = (syminfo.type == "stock")

textColor = color.orange

// =============================================================================
// === Moving Averages =========================================================
// =============================================================================
// PERF: lengths are selected first, then a SINGLE ta.sma is instantiated per MA.
// The old adjustForWeekly(ta.sma(close, 10), 4) helper evaluated BOTH the daily
// and the weekly average on every bar (function args are evaluated eagerly), so
// 10 rolling averages were maintained where 6 are needed — including a wasted
// 150- and 200-length SMA.
len10  = timeframe.isweekly ?  4 :  10
len50  = timeframe.isweekly ? 10 :  50
len150 = timeframe.isweekly ? 30 : 150
len200 = timeframe.isweekly ? 40 : 200

ma10  = ta.sma(close, len10)
ma20  = timeframe.isweekly ? ta.sma(close, 4) : ta.ema(close, 21)
ma50  = ta.sma(close, len50)
ma150 = ta.sma(close, len150)
ma200 = ta.sma(close, len200)

// =============================================================================
// === Fundamentals: fetched ONCE at global scope ==============================
// =============================================================================
// PERF: these were previously inside getMarketCap()/getFloatData(), each of
// which was called TWICE inside the barstate.islast block (once to size the
// table, once to fill it). That meant 4 request.financial + 4 request.security
// calls against a 40-request budget. They are now 2 request.financial calls.
//
// The old request.security(syminfo.tickerid, "D", close) was also a no-op on the
// timeframes where the table renders (daily/weekly) — `close` is the same value.
total_shares = request.financial(syminfo.tickerid, 'TOTAL_SHARES_OUTSTANDING', 'FQ', ignore_invalid_symbol = true)
shares_float = request.financial(syminfo.tickerid, 'FLOAT_SHARES_OUTSTANDING', 'FY', ignore_invalid_symbol = true)

market_cap   = na(total_shares) ? float(na) : total_shares * close
float_pct    = (na(shares_float) or na(total_shares) or total_shares <= 0 or shares_float <= 0) ? float(na) : shares_float / total_shares * 100

// =============================================================================
// === Earnings & Sales History =================================================
// =============================================================================
// request.earnings() updates on the bar a report is PUBLISHED; request.financial()
// updates on the bar the NEXT fiscal period BEGINS — different timing rules, so
// EPS and Revenue are tracked as two independent rolling histories rather than
// assumed to land on the same bar. Rows are matched by recency (newest with
// newest), not by a shared report date.
//
// Keeps 6 entries, not 4: the oldest DISPLAYED row still needs a prior value to
// compute its own QoQ growth against, so one extra slot is kept internally and
// never shown in the table.
eps_actual  = request.earnings(syminfo.tickerid, earnings.actual, ignore_invalid_symbol = true)
eps_forward = earnings.future_eps
rev_actual  = request.financial(syminfo.tickerid, "TOTAL_REVENUE", "FQ", ignore_invalid_symbol = true)
rev_forward = earnings.future_revenue

var array<float> eps_hist      = array.new_float(0)
var array<int>   eps_hist_time = array.new_int(0)
eps_new = not na(eps_actual) and (na(eps_actual[1]) or eps_actual != eps_actual[1])
if eps_new
    array.unshift(eps_hist, eps_actual)
    array.unshift(eps_hist_time, time)
    if array.size(eps_hist) > 6
        array.pop(eps_hist)
        array.pop(eps_hist_time)

var array<float> rev_hist = array.new_float(0)
rev_new = not na(rev_actual) and (na(rev_actual[1]) or rev_actual != rev_actual[1])
if rev_new
    array.unshift(rev_hist, rev_actual)
    if array.size(rev_hist) > 6
        array.pop(rev_hist)

// Net margin — TradingView provides this as its own field (NET_MARGIN) rather
// than net income and revenue needing to be fetched and divided separately.
// No forward/estimate equivalent exists for margin the way there does for EPS
// and Revenue, so the Forward row's margin cell is always "N/A" below — that's
// a real data gap, not a bug.
net_margin = request.financial(syminfo.tickerid, "NET_MARGIN", "FQ", ignore_invalid_symbol = true)

var array<float> margin_hist = array.new_float(0)
margin_new = not na(net_margin) and (na(net_margin[1]) or net_margin != net_margin[1])
if margin_new
    array.unshift(margin_hist, net_margin)
    if array.size(margin_hist) > 6
        array.pop(margin_hist)

// Returns [QoQ growth %, color] for history index i (0 = latest). na/white if
// that slot isn't filled yet (recent IPO, thin coverage) or there's no earlier
// entry to compare against.
histRow(array<float> hist, int i, float threshold) =>
    float val    = array.size(hist) > i     ? array.get(hist, i)     : float(na)
    float prev   = array.size(hist) > i + 1 ? array.get(hist, i + 1) : float(na)
    float growth = (na(val) or na(prev) or prev == 0) ? float(na) : (val - prev) / math.abs(prev) * 100
    color c      = na(growth) ? color.white : growth >= threshold ? color.green : growth < 0 ? color.red : color.white
    [growth, c]

// Margin gets its own rule: the RAW value is what's shown (it's already a
// percentage, not something to take a growth-rate OF), colored by whether it
// expanded or contracted vs. the prior quarter — not histRow's 30%-relative-
// growth bar, which a margin rarely clears either way even on an ordinary
// quarter, and would leave this column reading white almost always.
marginRow(array<float> hist, int i) =>
    float val  = array.size(hist) > i     ? array.get(hist, i)     : float(na)
    float prev = array.size(hist) > i + 1 ? array.get(hist, i + 1) : float(na)
    color c    = (na(val) or na(prev)) ? color.white : val >= prev ? color.green : color.red
    [val, c]

rowLabel(array<int> times, int i) =>
    array.size(times) > i ? str.format_time(array.get(times, i), "MMM yy") : "Q-" + str.tostring(i)

[eps_g0, eps_c0] = histRow(eps_hist, 0, earnings_growth_thresh)
[eps_g1, eps_c1] = histRow(eps_hist, 1, earnings_growth_thresh)
[eps_g2, eps_c2] = histRow(eps_hist, 2, earnings_growth_thresh)
[eps_g3, eps_c3] = histRow(eps_hist, 3, earnings_growth_thresh)

[rev_g0, rev_c0] = histRow(rev_hist, 0, earnings_growth_thresh)
[rev_g1, rev_c1] = histRow(rev_hist, 1, earnings_growth_thresh)
[rev_g2, rev_c2] = histRow(rev_hist, 2, earnings_growth_thresh)
[rev_g3, rev_c3] = histRow(rev_hist, 3, earnings_growth_thresh)

[margin_v0, margin_c0] = marginRow(margin_hist, 0)
[margin_v1, margin_c1] = marginRow(margin_hist, 1)
[margin_v2, margin_c2] = marginRow(margin_hist, 2)
[margin_v3, margin_c3] = marginRow(margin_hist, 3)

// Forward row: growth is the forward estimate vs. the latest ACTUAL (index 0) —
// "is the company guided/expected to keep accelerating from what it just
// reported," not vs. another estimate.
eps_fwd_prev   = array.size(eps_hist) > 0 ? array.get(eps_hist, 0) : float(na)
eps_fwd_growth = (na(eps_forward) or na(eps_fwd_prev) or eps_fwd_prev == 0) ? float(na) : (eps_forward - eps_fwd_prev) / math.abs(eps_fwd_prev) * 100
eps_fwd_color  = na(eps_fwd_growth) ? color.white : eps_fwd_growth >= earnings_growth_thresh ? color.green : eps_fwd_growth < 0 ? color.red : color.white

rev_fwd_prev   = array.size(rev_hist) > 0 ? array.get(rev_hist, 0) : float(na)
rev_fwd_growth = (na(rev_forward) or na(rev_fwd_prev) or rev_fwd_prev == 0) ? float(na) : (rev_forward - rev_fwd_prev) / math.abs(rev_fwd_prev) * 100
rev_fwd_color  = na(rev_fwd_growth) ? color.white : rev_fwd_growth >= earnings_growth_thresh ? color.green : rev_fwd_growth < 0 ? color.red : color.white

// =============================================================================
// === ADR =====================================================================
// =============================================================================
// PERF: the old getADR()/getADRPercentage() each wrapped ta.sma(high - low, n)
// in request.security(syminfo.tickerid, timeframe.period, ...) — a self-
// referential request against the same symbol AND the same timeframe. That is
// pure overhead (and is one of the cases that can return na). Removed.
//
// The two functions also used different lengths, instantiating two rolling
// averages. They are identical on daily/weekly (the only timeframes the table
// renders on), so a single series is kept. Intraday now uses the extended
// length for both the $ and % readouts.
adr_len = (timeframe.isdaily or timeframe.isweekly) ? adr_length_input : int(2.2 * adr_length_input)
adr_abs = ta.sma(high - low, adr_len)
adr_pct = close > 0 ? adr_abs / close * 100 : float(na)

adr_pct_color = na(adr_pct) ? textColor : adr_pct > 3.5 ? color.green : adr_pct > 2 ? color.white : textColor

// Dollar volume, RVol, and their color tiers used to be duplicated here in
// full (a second copy of everything in dollar_volume.py) just to fill one
// table cell below. Removed — that data already has its own dedicated pane
// (dollar_volume.py); this script no longer computes or shows it.

// =============================================================================
// === String Formatters (no series calls — safe to call inside barstate.islast)
// =============================================================================
fmtRounded(float v) =>
    string s = "N/A"
    if not na(v)
        if v > 1e9
            s := str.tostring(math.round(v / 1e9)) + "B"
        else if v > 1e6
            s := str.tostring(math.round(v / 1e6)) + "M"
        else
            s := str.tostring(math.round(v))
    s

fmtDecimal(float v) =>
    string s = "N/A"
    if not na(v)
        if v >= 1e9
            s := str.tostring(v / 1e9, "#.##") + "B"
        else if v >= 1e6
            s := str.tostring(v / 1e6, "#.##") + "M"
        else if v >= 1e3
            s := str.tostring(v / 1e3, "#.##") + "K"
        else
            s := str.tostring(v, "#.##")
    s

//----------------------------------------------------------------------------------------------------------------------------------------
// Plot MAs at the global scope
p10  = plot(ma10,  title = 'MA 10',  color=#5d606b,  display = MA10  ? display.pane : display.none)
p21  = plot(ma20,  title = 'MA 21',  color=#cfcfa6,  display = MA21  ? display.pane : display.none)
p50  = plot(ma50,  title = 'MA 50',  color=#ffffff,  display = MA50  ? display.pane : display.none)
p150 = plot(ma150, title = 'MA 150', color=#81e4eb,  display = MA150 ? display.pane : display.none)
p200 = plot(ma200, title = 'MA 200', color=#b71c1c,  display = MA200 ? display.pane : display.none)

// Fill areas between MAs
fill_color_2110 = if timeframe.isweekly
    color.new(color.black, 100)
else if ma10 > ma20
    #58c79c57
else
    #cb3b3b59

fill_color_week = timeframe.isweekly ? (ma50 > ma10 ? color.new(color.rgb(252, 137, 137), 80) : color.new(color.green, 80)) : color.new(color.black, 100)
fill(p10, p50, color=fill_color_week)
fill(p10, p21, color=fill_color_2110)

// EMA21 dynamic stdDev bands
priceDistance = math.abs(close - ma20)
stdDev20 = ta.stdev(close, 20)

baseMultiplier = 2.0
maxDistance = 5 * stdDev20
// Guard: a flat 20-bar window makes maxDistance 0 and the ratio inf/na.
distRatio = maxDistance > 0 ? math.min(priceDistance / maxDistance, 0.5) : 0.0
dynamicMultiplier = baseMultiplier * (1 - distRatio) + 0.5

ma20Upper = ma20 + dynamicMultiplier * stdDev20
ma20Lower = ma20 - dynamicMultiplier * stdDev20

p21Upper = plot(timeframe.isweekly ? na : ma20Upper, color=color.new(color.white, 80), display=ema21_bands_input ? display.pane : display.none, linewidth=1, title="21MA Upper Bounce")
p21Lower = plot(timeframe.isweekly ? na : ma20Lower, color=color.new(color.white, 80), display=ema21_bands_input ? display.pane : display.none, linewidth=1, title="21MA Lower Bounce")

fill_color_bounce = color.new(color.blue, 90)
fill(p21Upper, p21Lower, color=fill_color_bounce, display=ema21_bands_input ? display.all : display.none)

// =============================================================================
// === Price Bar Color =========================================================
// =============================================================================
dayRange = high - low

paletteColor = color.rgb(255, 255, 255, 44)
if high <= high[1] and low >= low[1]
    paletteColor := color.rgb(255, 255, 255, 11)
else if close > high - (dayRange * 0.3)
    paletteColor := #4ccc50
else if close > high - (dayRange * 0.5)
    paletteColor := #2186709c
else if close < low + (dayRange * 0.3)
    paletteColor := #ee3535
else if close < low + (dayRange * 0.5)
    paletteColor := #f7786195

plotbar(close, high, low, close, title = 'Candles', color = paletteColor)

// =============================================================================
// === Background: NDFD Market Condition =======================================
// =============================================================================
dailyCloseNCFD = request.security("NDFD", "D", close)
color bgColor = na

if timeframe.isintraday or timeframe.isdaily
    if dailyCloseNCFD < 10
        bgColor := color.new(color.green, 90)
    else if dailyCloseNCFD > 85
        bgColor := color.new(color.red, 90)

bgcolor(bgColor)

// =============================================================================
// === Table: Technical Data ===================================================
// =============================================================================
// PERF / BUG: the old version called table.delete() + table.new() inside
// barstate.islast. On a live bar that fires on EVERY tick, so the table was torn
// down and rebuilt continuously.
//
// Worse, `rowCount` and `currentRow` were declared `var int` inside that block.
// `var` persists across bars, so on every realtime tick rowCount grew by ~8
// without ever resetting, and currentRow marched past the end of the table —
// meaning the row count fed to table.new() climbed without bound for as long as
// the chart stayed open.
//
// Fixed: one table allocated once at a fixed maximum size (7 rows is the most
// the layout can ever use, now that Vol is gone), counters are plain locals
// that reset each bar, and the alignment loop only touches rows that were
// actually written.
tablePosition = timeframe.isminutes ? position.bottom_right : position.top_right
tableSize     = size.small
tableBgColor  = color.rgb(34, 37, 44, 100)

var table techTable = table.new(tablePosition, 2, 7, bgcolor = tableBgColor)

if barstate.islast and (timeframe.isdaily or timeframe.isweekly)
    int currentRow = 0

    // Market Cap
    if not na(market_cap)
        marketCapColor = market_cap > 500e9 or market_cap < 100e6 ? color.red : market_cap > 100e9 or market_cap < 300e6 ? color.yellow : textColor
        table.cell(techTable, 0, currentRow, "Market Cap", text_color = textColor, text_size = tableSize)
        table.cell(techTable, 1, currentRow, fmtRounded(market_cap), text_color = marketCapColor, text_size = tableSize)
        currentRow += 1

    // Float
    if not na(shares_float) and not na(float_pct)
        floatColor = shares_float < 100e6 ? color.white : textColor
        table.cell(techTable, 0, currentRow, "Shares Float", text_color = textColor, text_size = tableSize)
        table.cell(techTable, 1, currentRow, fmtDecimal(shares_float) + " ( " + str.tostring(float_pct, "#.#") + "% )", text_color = floatColor, text_size = tableSize)
        currentRow += 1

    // ADR %
    table.cell(techTable, 0, currentRow, "ADR", text_color = textColor, text_size = tableSize)
    table.cell(techTable, 1, currentRow, na(adr_pct) ? "N/A" : str.tostring(adr_pct, "#.##") + "%", text_color = adr_pct_color, text_size = tableSize)
    currentRow += 1

    // xADR ($)
    table.cell(techTable, 0, currentRow, "xADR", text_color = color.white, text_size = tableSize)
    table.cell(techTable, 1, currentRow, na(adr_abs) ? "N/A" : "$" + str.tostring(adr_abs, "#.##"), text_color = color.white, text_size = tableSize)
    currentRow += 1

    // %ADR — share of one ADR consumed by today's move.
    // Uses the raw ADR series directly. The old version ran the formatted string
    // back through str.tonumber(), which both cost a parse and silently rounded
    // the divisor to 2 decimal places.
    adr_used_pct       = (na(adr_abs) or adr_abs == 0) ? float(na) : math.abs(close - close[1]) / adr_abs * 100
    adr_used_pct_color = na(adr_used_pct) ? color.white : adr_used_pct > 90 ? color.red : color.white
    table.cell(techTable, 0, currentRow, "%ADR", text_color = textColor, text_size = tableSize)
    table.cell(techTable, 1, currentRow, na(adr_used_pct) ? "N/A" : str.tostring(adr_used_pct, "#.##") + "%", text_color = adr_used_pct_color, text_size = tableSize)
    currentRow += 1

    // Sector
    if not na(syminfo.sector) and isStock
        table.cell(techTable, 0, currentRow, "Sector", text_color = textColor, text_size = tableSize)
        table.cell(techTable, 1, currentRow, syminfo.sector, text_color = textColor, text_size = tableSize)
        currentRow += 1

    // Industry
    if not na(syminfo.industry) and isStock
        table.cell(techTable, 0, currentRow, "Ind. Grp", text_color = textColor, text_size = tableSize)
        table.cell(techTable, 1, currentRow, syminfo.industry, text_color = textColor, text_size = tableSize)
        currentRow += 1

    // Text alignment — only over rows that exist
    for row = 0 to currentRow - 1
        table.cell_set_text_halign(techTable, 0, row, text.align_right)
        table.cell_set_text_halign(techTable, 1, row, text.align_left)

// =============================================================================
// === Table: Earnings & Sales ==================================================
// =============================================================================
// Anchored bottom_right so it sits below the technical-data table above
// (top_right) — Pine tables only snap to 9 fixed positions, there's no manual
// stacking, so this is how "underneath the existing table" is achieved.
//
// Green/red per Bang: QoQ growth >= earnings_growth_thresh (default 30%) reads
// green, anything short of that (including a decline) reads red. Same rule
// for the Forward row, just measured against the latest actual instead of
// another quarter.
var table earnTable = table.new(position.bottom_right, 4, 6, bgcolor = tableBgColor)

if show_earnings_table and barstate.islast and (timeframe.isdaily or timeframe.isweekly) and isStock
    table.cell(earnTable, 0, 0, "Qtr", text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 1, 0, "EPS",  text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 2, 0, "Sales", text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 3, 0, "Margin", text_color = textColor, text_size = tableSize)

    // Forward — estimate for the next, not-yet-reported quarter. No forward
    // margin field exists on TradingView, so that cell is always N/A.
    table.cell(earnTable, 0, 1, "Fwd", text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 1, na(eps_fwd_growth) ? "N/A" : str.tostring(eps_fwd_growth, "0") + "%", text_color = eps_fwd_color, text_size = tableSize)
    table.cell(earnTable, 2, 1, na(rev_fwd_growth) ? "N/A" : str.tostring(rev_fwd_growth, "0") + "%", text_color = rev_fwd_color, text_size = tableSize)
    table.cell(earnTable, 3, 1, "N/A", text_color = color.white, text_size = tableSize)

    // Latest reported quarter through 3 quarters back
    table.cell(earnTable, 0, 2, rowLabel(eps_hist_time, 0), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 2, na(eps_g0) ? "N/A" : str.tostring(eps_g0, "0") + "%", text_color = eps_c0, text_size = tableSize)
    table.cell(earnTable, 2, 2, na(rev_g0) ? "N/A" : str.tostring(rev_g0, "0") + "%", text_color = rev_c0, text_size = tableSize)
    table.cell(earnTable, 3, 2, na(margin_v0) ? "N/A" : str.tostring(margin_v0, "0") + "%", text_color = margin_c0, text_size = tableSize)

    table.cell(earnTable, 0, 3, rowLabel(eps_hist_time, 1), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 3, na(eps_g1) ? "N/A" : str.tostring(eps_g1, "0") + "%", text_color = eps_c1, text_size = tableSize)
    table.cell(earnTable, 2, 3, na(rev_g1) ? "N/A" : str.tostring(rev_g1, "0") + "%", text_color = rev_c1, text_size = tableSize)
    table.cell(earnTable, 3, 3, na(margin_v1) ? "N/A" : str.tostring(margin_v1, "0") + "%", text_color = margin_c1, text_size = tableSize)

    table.cell(earnTable, 0, 4, rowLabel(eps_hist_time, 2), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 4, na(eps_g2) ? "N/A" : str.tostring(eps_g2, "0") + "%", text_color = eps_c2, text_size = tableSize)
    table.cell(earnTable, 2, 4, na(rev_g2) ? "N/A" : str.tostring(rev_g2, "0") + "%", text_color = rev_c2, text_size = tableSize)
    table.cell(earnTable, 3, 4, na(margin_v2) ? "N/A" : str.tostring(margin_v2, "0") + "%", text_color = margin_c2, text_size = tableSize)

    table.cell(earnTable, 0, 5, rowLabel(eps_hist_time, 3), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 5, na(eps_g3) ? "N/A" : str.tostring(eps_g3, "0") + "%", text_color = eps_c3, text_size = tableSize)
    table.cell(earnTable, 2, 5, na(rev_g3) ? "N/A" : str.tostring(rev_g3, "0") + "%", text_color = rev_c3, text_size = tableSize)
    table.cell(earnTable, 3, 5, na(margin_v3) ? "N/A" : str.tostring(margin_v3, "0") + "%", text_color = margin_c3, text_size = tableSize)

    for earnRow = 0 to 5
        table.cell_set_text_halign(earnTable, 0, earnRow, text.align_right)
        table.cell_set_text_halign(earnTable, 1, earnRow, text.align_left)
        table.cell_set_text_halign(earnTable, 2, earnRow, text.align_left)
        table.cell_set_text_halign(earnTable, 3, earnRow, text.align_left)
else if barstate.islast
    // Backstop on top of the condition above (which already means no cell is
    // ever written on intraday): clears out whatever the table last held if the
    // person switches FROM daily/weekly TO intraday mid-session, rather than
    // relying only on "never populated" for a table object that already exists.
    table.clear(earnTable, 0, 0, 3, 5)

// =============================================================================
// === Table: Earnings & Sales ==================================================
// =============================================================================
// Anchored bottom_right so it sits below the technical-data table above
// (top_right) — Pine tables only snap to 9 fixed positions, there's no manual
// stacking, so this is how "underneath the existing table" is achieved.
//
// Green/red per Bang: QoQ growth >= earnings_growth_thresh (default 30%) reads
// green, anything short of that (including a decline) reads red. Same rule
// for the Forward row, just measured against the latest actual instead of
// another quarter.
var table earnTable = table.new(position.bottom_right, 4, 6, bgcolor = tableBgColor)

if show_earnings_table and barstate.islast and (timeframe.isdaily or timeframe.isweekly) and isStock
    table.cell(earnTable, 0, 0, "Qtr", text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 1, 0, "EPS",  text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 2, 0, "Sales", text_color = textColor, text_size = tableSize)
    table.cell(earnTable, 3, 0, "Margin", text_color = textColor, text_size = tableSize)

    // Forward — estimate for the next, not-yet-reported quarter. No forward
    // margin field exists on TradingView, so that cell is always N/A.
    table.cell(earnTable, 0, 1, "Fwd", text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 1, na(eps_fwd_growth) ? "N/A" : str.tostring(eps_fwd_growth, "0") + "%", text_color = eps_fwd_color, text_size = tableSize)
    table.cell(earnTable, 2, 1, na(rev_fwd_growth) ? "N/A" : str.tostring(rev_fwd_growth, "0") + "%", text_color = rev_fwd_color, text_size = tableSize)
    table.cell(earnTable, 3, 1, "N/A", text_color = color.white, text_size = tableSize)

    // Latest reported quarter through 3 quarters back
    table.cell(earnTable, 0, 2, rowLabel(eps_hist_time, 0), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 2, na(eps_g0) ? "N/A" : str.tostring(eps_g0, "0") + "%", text_color = eps_c0, text_size = tableSize)
    table.cell(earnTable, 2, 2, na(rev_g0) ? "N/A" : str.tostring(rev_g0, "0") + "%", text_color = rev_c0, text_size = tableSize)
    table.cell(earnTable, 3, 2, na(margin_v0) ? "N/A" : str.tostring(margin_v0, "0") + "%", text_color = margin_c0, text_size = tableSize)

    table.cell(earnTable, 0, 3, rowLabel(eps_hist_time, 1), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 3, na(eps_g1) ? "N/A" : str.tostring(eps_g1, "0") + "%", text_color = eps_c1, text_size = tableSize)
    table.cell(earnTable, 2, 3, na(rev_g1) ? "N/A" : str.tostring(rev_g1, "0") + "%", text_color = rev_c1, text_size = tableSize)
    table.cell(earnTable, 3, 3, na(margin_v1) ? "N/A" : str.tostring(margin_v1, "0") + "%", text_color = margin_c1, text_size = tableSize)

    table.cell(earnTable, 0, 4, rowLabel(eps_hist_time, 2), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 4, na(eps_g2) ? "N/A" : str.tostring(eps_g2, "0") + "%", text_color = eps_c2, text_size = tableSize)
    table.cell(earnTable, 2, 4, na(rev_g2) ? "N/A" : str.tostring(rev_g2, "0") + "%", text_color = rev_c2, text_size = tableSize)
    table.cell(earnTable, 3, 4, na(margin_v2) ? "N/A" : str.tostring(margin_v2, "0") + "%", text_color = margin_c2, text_size = tableSize)

    table.cell(earnTable, 0, 5, rowLabel(eps_hist_time, 3), text_color = color.white, text_size = tableSize)
    table.cell(earnTable, 1, 5, na(eps_g3) ? "N/A" : str.tostring(eps_g3, "0") + "%", text_color = eps_c3, text_size = tableSize)
    table.cell(earnTable, 2, 5, na(rev_g3) ? "N/A" : str.tostring(rev_g3, "0") + "%", text_color = rev_c3, text_size = tableSize)
    table.cell(earnTable, 3, 5, na(margin_v3) ? "N/A" : str.tostring(margin_v3, "0") + "%", text_color = margin_c3, text_size = tableSize)

    for earnRow = 0 to 5
        table.cell_set_text_halign(earnTable, 0, earnRow, text.align_right)
        table.cell_set_text_halign(earnTable, 1, earnRow, text.align_left)
        table.cell_set_text_halign(earnTable, 2, earnRow, text.align_left)
        table.cell_set_text_halign(earnTable, 3, earnRow, text.align_left)
else if barstate.islast
    // Backstop on top of the condition above (which already means no cell is
    // ever written on intraday): clears out whatever the table last held if the
    // person switches FROM daily/weekly TO intraday mid-session, rather than
    // relying only on "never populated" for a table object that already exists.
    table.clear(earnTable, 0, 0, 3, 5)