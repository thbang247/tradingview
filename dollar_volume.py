//@version=6
indicator('Dollar Volume', overlay = false, format = format.volume)

// =============================================================================
// === Inputs ==================================================================
// =============================================================================
line_width_input      = input.int(3,   "Line Width",              group="Display")

daily_avg_length      = input.int(50,  "Daily Average Length",    group="Averages")
weekly_avg_length     = input.int(10,  "Weekly Average Length",   group="Averages")

// Volume surge thresholds vs rolling average (daily / intraday)
daily_2x_threshold    = input.float(2.0, "Daily 2× Surge",        group="Thresholds")
daily_5x_threshold    = input.float(5.0, "Daily 5× Surge",        group="Thresholds")
// Volume surge thresholds vs rolling average (weekly)
weekly_15x_threshold  = input.float(1.5, "Weekly 1.5× Surge",     group="Thresholds")
weekly_3x_threshold   = input.float(3.0, "Weekly 3× Surge",       group="Thresholds")

// Relative Volume at Time — appended after the existing inputs so the seven
// above keep their saved positions on charts that already have this script on.
rvol_show       = input.bool(true,   "Show RVol at Time",                      group="Relative Volume at Time")
rvol_anchor     = input.timeframe("D", "Anchor Timeframe",                      group="Relative Volume at Time")
rvol_length     = input.int(10, "Historical Periods", minval=1, maxval=50,      group="Relative Volume at Time")
rvol_cumulative = input.bool(true,   "Cumulative (else this bar only)",         group="Relative Volume at Time")
rvol_use_dollar = input.bool(false,  "Use dollar volume (off = share volume)",  group="Relative Volume at Time")

// Accumulation / Distribution — appended after the RVOL group for the same reason.
ud_length        = input.int(50,   "U/D Volume Length",  minval=2,          group="Accumulation / Distribution")
ud_accum_level   = input.float(1.25, "Accumulation Threshold",              group="Accumulation / Distribution")
ud_distrib_level = input.float(0.85, "Distribution Threshold",              group="Accumulation / Distribution")

// =============================================================================
// === Dollar Volume ===========================================================
// =============================================================================
// Default: dollar volume = price × share volume.
// Special cases:
//   IXIC — use TVOLQ (Nasdaq composite dollar volume, already in $ terms)
//   GOLD — use GLD proxy volume × close (GOLD has no native volume)
//
// NOTE: the previous version placed these request.security calls inside
// `if syminfo.ticker == ...` blocks with a comment claiming that avoided
// "wasteful security calls on every symbol". It does not — request.* calls are
// resolved for the whole script regardless of which runtime branch is taken, so
// both feeds were requested on every symbol either way. Hoisting them to global
// scope costs nothing extra and drops the conditional-request warning.
// ignore_invalid_symbol added so a missing feed yields na instead of an error.
is_ixic = syminfo.ticker == 'IXIC'
is_gold = syminfo.ticker == 'GOLD'

tvolq_close = request.security('TVOLQ', timeframe.period, close,  ignore_invalid_symbol = true)
gld_volume  = request.security('GLD',   timeframe.period, volume, ignore_invalid_symbol = true)

vol = is_ixic ? tvolq_close : is_gold ? gld_volume * close : volume * close

// Share-volume equivalent, carrying the SAME substitutions. Needed because the
// RVol source toggle can select share volume, and raw `volume` is na on IXIC —
// which is the entire reason the TVOLQ substitution exists for `vol`.
// For GOLD the analogue is GLD's own share volume (no × close).
// For IXIC there is no separate share feed, so TVOLQ is reused: RVol is a ratio
// of a series against its own history, so whatever units TVOLQ carries cancel.
vol_shares = is_ixic ? tvolq_close : is_gold ? gld_volume : volume

// PERF: lengths resolved first so one accumulator is built per average. The old
// form ran ta.sma at the default length then reassigned inside
// `if timeframe.isweekly` with a second ta.sma — four rolling averages
// maintained where two are needed, with ta.* state updated inside a conditional.
avg_len_long  = timeframe.isweekly ? weekly_avg_length : daily_avg_length
avg_len_short = timeframe.isweekly ? 4 : 10

volume_avg_long  = ta.sma(vol, avg_len_long)
volume_avg_short = ta.sma(vol, avg_len_short)

// ta.sma yields na until its full window is available, so on a recent IPO the
// 50-bar average is undefined for the first 49 bars — which left compare_vol na,
// made every `bar_vol > cmp_vol` test false, and painted the whole early history
// dim white with no average line. Fall back to the short average while the long
// one is still filling.
volume_avg = na(volume_avg_long) ? volume_avg_short : volume_avg_long

// =============================================================================
// === Direction ===============================================================
// =============================================================================
// Hoisted here because both the bar colour and the U/D ratio below need them.
up_day   = close > close[1]
down_day = close < close[1]

// =============================================================================
// === Relative Volume at Time =================================================
// =============================================================================
// Compares volume at a given offset from the period anchor against the average
// volume at that SAME offset over the last N periods — so at 10:15 on a 5m chart
// it measures today's first 45 minutes against the first 45 minutes of the prior
// N sessions, rather than against a full-day average that 10:15 can never reach.
//
// Implementation: a rolling volume profile held in a matrix, one row per period,
// one column per bar-offset within the period. Each bar writes a single cell and
// reads N cells, so cost is O(rvol_length) per bar with no deep history access —
// important, because the obvious alternative (indexing `cum[bar_index - target]`)
// would need max_bars_back in the thousands on a 1-minute chart.
//
// The matrix stores PER-BAR volume, never the running total. Two ratios come out
// of it:
//   rvol_bar — this bar vs the same offset in prior periods. Drives the bar
//              colour, because each histogram column IS one bar.
//   rvol_cum_ratio — session-to-date vs the same point in prior sessions. Drives
//              the table when "Cumulative" is on.
// The cumulative average is accumulated as a running sum of the per-bar averages
// rather than stored separately: averaging is linear, so the mean cumulative at
// offset k equals the sum of the mean per-bar values at offsets 0..k. That keeps
// one matrix instead of two, still O(rvol_length) per bar.
//
// row_len tracks how many columns each row actually filled. On a short session
// (half day) the requested offset may not exist, so the read clamps to that
// row's last valid column — TradingView's documented behaviour: if a historical
// period has no bar at the offset, it uses the last one before it.
//
// DEGENERATE CASE, and a useful one: when the anchor is at or below the chart
// timeframe (e.g. a "D" anchor on a daily chart) the period resets every bar, so
// each row holds exactly one bar, cumulative and per-bar collapse to the same
// number, and this becomes plain relative volume — today over the average of the
// previous N days. Because the current row is excluded from that average, it
// lands on ta.sma(volume, N)[1], the formula behind the screener's Relative
// Volume column. With share volume selected, the daily reading reconciles.
rvol_max_cols = 1000   // bar-offsets tracked per period; deeper offsets clamp

// BUGFIX: this read `volume` directly, bypassing the IXIC/GOLD substitutions
// applied to `vol`. On IXIC raw `volume` is na, so every cell written into the
// profile matrix was na, rvol_avg_bar came back na, and the table read "n/a" —
// even though the histogram itself was correctly plotting TVOLQ.
rvol_src = rvol_use_dollar ? vol : vol_shares

new_period = timeframe.change(rvol_anchor)

var float         rvol_cum     = 0.0
var float         rvol_avg_cum = 0.0
var int           rvol_col     = 0
var int           rvol_row     = 0
var matrix<float> rvol_profile = matrix.new<float>(rvol_length + 1, rvol_max_cols, na)
var array<int>    rvol_row_len = array.new_int(rvol_length + 1, 0)

if bar_index == 0
    rvol_cum     := rvol_src
    rvol_avg_cum := 0.0
    rvol_col     := 0
else if new_period
    rvol_cum     := rvol_src
    rvol_avg_cum := 0.0
    rvol_col     := 0
    rvol_row     := (rvol_row + 1) % (rvol_length + 1)   // circular: no row clearing
    array.set(rvol_row_len, rvol_row, 0)
else
    rvol_cum := rvol_cum + rvol_src
    rvol_col := rvol_col + 1

rvol_c = math.min(rvol_col, rvol_max_cols - 1)

matrix.set(rvol_profile, rvol_row, rvol_c, rvol_src)
array.set(rvol_row_len, rvol_row, rvol_c + 1)

// Average the same offset across every row except the one being built
float rvol_sum = 0.0
int   rvol_n   = 0
for r = 0 to rvol_length
    if r != rvol_row
        rl = array.get(rvol_row_len, r)
        if rl > 0
            v = matrix.get(rvol_profile, r, math.min(rvol_c, rl - 1))
            if not na(v)
                rvol_sum += v
                rvol_n   += 1

rvol_avg_bar = rvol_n > 0 ? rvol_sum / rvol_n : float(na)

if not na(rvol_avg_bar)
    rvol_avg_cum := rvol_avg_cum + rvol_avg_bar

rvol_bar       = (not na(rvol_avg_bar) and rvol_avg_bar > 0) ? rvol_src / rvol_avg_bar : float(na)
rvol_cum_ratio = rvol_avg_cum > 0 ? rvol_cum / rvol_avg_cum : float(na)

// Table reading honours the Cumulative toggle; the bar colour never does.
rvol_at_time = rvol_cumulative ? rvol_cum_ratio : rvol_bar

// =============================================================================
// === Bar Color Logic =========================================================
// =============================================================================
// TWO INDEPENDENT AXES, because the two questions genuinely disagree and each
// one alone is incomplete:
//
//   HUE     = RELATIVE VOLUME. Is this bar busy for its own slot in the session,
//             measured against the same offset in prior periods? Green/aqua/blue
//             on an up close, red/purple/maroon on a down close, grey below 1x.
//   OPACITY = VS THE 50-BAR AVERAGE. Solid when the bar clears its long-run
//             dollar-volume average, translucent when it does not.
//
// These are not redundant. RVol is same-offset and excludes the current bar; the
// 50-bar average is a trailing absolute that includes it. QNST showed the split
// exactly: a bar sitting above its 50-day baseline while running at 0.63x the
// recent pace, because an earnings spike ten sessions back inflated the RVol
// denominator. Hue alone hid the first fact; the old colouring hid the second.
//
// Read it as: hue = is this bar hot RIGHT NOW, opacity = is it big in absolute
// terms. Solid blue is both. Faint blue is a surge off a low base. Solid grey is
// a heavy but unremarkable bar. Faint grey is nothing happening.
//
// Tier boundaries are unchanged (2x / 5x daily, 1.5x / 3x weekly) but they now
// multiply a same-offset historical average rather than a trailing mean that
// contained the bar being measured — the old ta.sma(vol, 50) denominator was
// dragged up ~8% by a genuine 5x day, so the top tier fired late.
//
// REMOVED earlier: the SPX/IXIC/IWM/ARKK/FFTY special case comparing indices
// against the previous bar. A relative-volume ratio is self-normalising against
// the feed's own history, so indices now take the same path as everything else.

// Base hues carry no alpha of their own — opacity is applied once, below, so the
// two axes stay independent.
C_QUIET   = #8b929c                      // below 1x RVol, either direction
C_UP_HI   = #0039d4                      // up + extreme surge
C_UP_MID  = #22c3d4                      // up + moderate surge
C_UP_LOW  = #75da56                      // up + above normal
C_DN_HI   = #8b1a1a                      // down + extreme surge
C_DN_MID  = #b950b9                      // down + moderate surge
C_DN_LOW  = #e67771                      // down + above normal

getVolBarHue(float ratio, bool is_up, float surge_low, float surge_high) =>
    color c = C_QUIET
    if na(ratio) or ratio < 1.0
        c := C_QUIET
    else if is_up
        c := ratio > surge_high ? C_UP_HI : ratio > surge_low ? C_UP_MID : C_UP_LOW
    else
        c := ratio > surge_high ? C_DN_HI : ratio > surge_low ? C_DN_MID : C_DN_LOW
    c

// Select thresholds by timeframe
surge_low  = timeframe.isweekly ? weekly_15x_threshold : daily_2x_threshold
surge_high = timeframe.isweekly ? weekly_3x_threshold  : daily_5x_threshold

// Short-history fallback, matching the pattern used elsewhere in the suite: until
// enough prior periods exist for a relative reading, fall back to the old
// vol / long-average comparison so early bars still carry colour.
fallback_ratio = (not na(volume_avg) and volume_avg > 0) ? vol / volume_avg : float(na)
color_ratio    = na(rvol_bar) ? fallback_ratio : rvol_bar

// Compared against volume_avg rather than volume_avg[1] deliberately: volume_avg
// is the white line drawn on this pane, so the opacity flips exactly where the
// eye sees the bar cross it. Excluding the current bar would be defensible
// arithmetic but would put the colour change in the wrong visual place.
vol_above_avg = not na(volume_avg) and vol >= volume_avg

bar_hue   = getVolBarHue(color_ratio, up_day, surge_low, surge_high)
bar_color = color.new(bar_hue, vol_above_avg ? 0 : 55)

// =============================================================================
// === Up/Down Volume Ratio ====================================================
// =============================================================================
// All three measures below run on `vol` — this script's dollar volume, including
// the IXIC/GOLD substitutions. IBD and Minervini define these on share volume;
// over a 50-bar window the price weighting shifts the U/D ratio only slightly,
// and over a 10-bar window it's negligible. Swap `vol` for `volume` throughout
// this section if you want to reconcile exactly with published figures.
//
// Deliberately NOT used here: ta.accdist, ta.cmf, ta.mfi. All three infer intent
// from where price closed inside its own bar, which makes them gap-blind — a
// stock that gaps up 8% and closes mid-range scores as distribution even though
// the gap WAS the accumulation. On daily bars in high-ADR names that's most of
// the information. U/D ratio only asks whether the close was up or down, so gaps
// land in the right bucket at full weight.

// --- Up/Down Volume Ratio (O'Neil / IBD) ---
// Volume on advancing closes over volume on declining closes. Above 1.0 = more
// volume trading into strength. IBD treats roughly 1.25+ as leader-quality.
ud_up_sum   = math.sum(up_day   ? vol : 0.0, ud_length)
ud_down_sum = math.sum(down_day ? vol : 0.0, ud_length)
ud_ratio    = ud_down_sum > 0 ? ud_up_sum / ud_down_sum : float(na)

// =============================================================================
// === Readout Table ===========================================================
// =============================================================================
// Colour coding:
//   RVol@T  — same hue scale as the volume bars, at full opacity
//   U/D     — lime / green above the accumulation line, yellow neutral, red below
//             the distribution line: a red-to-green axis, since it's a scalar
//   Vol     — moved here from price_overlay.py's table, which used to duplicate
//             this whole script just to show this one cell. Reuses
//             volume_avg_short, already computed above — no new calculation.
ud_color = na(ud_ratio) ? color.new(color.white, 40) : ud_ratio >= ud_accum_level ? color.lime : ud_ratio >= 1.0 ? #75da56 : ud_ratio >= ud_distrib_level ? color.yellow : color.rgb(255, 80, 80)

// Cell colour derives from the number the cell SHOWS, not from bar_color. They
// are identical on a daily chart, but intraday the cell shows cumulative session
// pace while bar_color reflects this single bar — borrowing bar_color there would
// print a green 0.63x.
rvol_cell_color = getVolBarHue(rvol_at_time, up_day, surge_low, surge_high)

label_color = color.new(color.white, 30)

// Small pure formatter, ported from price_overlay.py. No series calls, so it's
// safe to duplicate — unlike the threshold/ratio logic that used to live over
// there, this has no meaningful "drift out of sync" risk.
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

var table rvol_table = na
if barstate.isfirst and rvol_show
    rvol_table := table.new(position.top_right, 2, 3)

if barstate.islast and rvol_show
    table.cell(rvol_table, 0, 0, "RVol@T", text_color = label_color, text_size = size.normal)
    table.cell(rvol_table, 1, 0, na(rvol_at_time) ? "n/a" : str.tostring(rvol_at_time, "0.00") + "x", text_color = rvol_cell_color, text_size = size.normal)

    table.cell(rvol_table, 0, 1, "U/D", text_color = label_color, text_size = size.normal)
    table.cell(rvol_table, 1, 1, na(ud_ratio) ? "n/a" : str.tostring(ud_ratio, "0.00"), text_color = ud_color, text_size = size.normal)

    table.cell(rvol_table, 0, 2, "Vol", text_color = label_color, text_size = size.normal)
    table.cell(rvol_table, 1, 2, "$" + fmtDecimal(volume_avg_short), text_color = color.white, text_size = size.normal)

    for row = 0 to 2
        table.cell_set_text_halign(rvol_table, 0, row, text.align_right)
        table.cell_set_text_halign(rvol_table, 1, row, text.align_left)

// =============================================================================
// === Plots ===================================================================
// =============================================================================
plot(vol,        style=plot.style_histogram, linewidth=math.max(1, line_width_input), color=bar_color)
plot(volume_avg, color=color.white)
