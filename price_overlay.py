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
