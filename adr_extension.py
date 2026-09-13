//@version=6
indicator("ADR Extension", overlay=false)

// =============================================================================
// === Inputs ==================================================================
// =============================================================================

// --- MA / ADR lengths ---
adr_length              = input.int(14,  "ADR Length",    group="Lengths")
ma_50_length            = input.int(50,  "MA 50 Length",  group="Lengths")
ma_10_length            = input.int(10,  "MA 10 Length (Extension smoothing)", group="Lengths")

// --- Extension thresholds ---
extreme_threshold       = input.float(7.0, "Extreme Extension Threshold (red)",  group="Thresholds")
high_threshold          = input.float(4.0, "High Extension Threshold (yellow)",  group="Thresholds")

// --- Extreme lookback windows ---
lookback_200            = input.int(150, "Extreme Lookback (long)",  group="Thresholds")
lookback_50             = input.int(20,  "Extreme Lookback (short)", group="Thresholds")

// --- Trend start (symmetric: uptrend green / downtrend red) ---
// Appended at the end of the input list so existing saved settings keep their
// positions. strength_ramp_bars is kept but unused — the ramp is now a fixed
// day-3/day-4/day-5+ schedule (see the color cascade below), not a tunable
// length — but it's a mid-list input, so removing it would silently shift
// show_weakness onto the wrong saved slot. Relabeled "(unused)" instead,
// same pattern as the dead inputs already retained in ma_stats.pine.
show_strength      = input.bool(true, "Highlight Uptrend Start",                  group="Trend Start")
strength_min_days  = input.int(3,   "Min Consecutive Days",       minval=2,       group="Trend Start")
strength_base_max  = input.float(1.0, "Max |Extension| Where Streak Began (ADR)", group="Trend Start")
strength_ramp_bars = input.int(5,   "(unused)",                   minval=1,       group="Trend Start")
show_weakness      = input.bool(true, "Highlight Downtrend Start",                group="Trend Start")

// =============================================================================
// === Extension Factor (distance to 50MA, scaled by ADR) ======================
// =============================================================================
ma50_full     = ta.sma(close, ma_50_length)
// Fallback: ta.sma yields na until its window fills, so on a recent IPO the
// 50MA is undefined for the first 49 bars and the whole pane stays blank.
// A fixed 10 is used rather than ma_10_length — that input is the *extension*
// smoothing period, and coupling the two would silently move this MA if the
// smoothing were retuned. Hardcoded rather than a new input so saved indicator
// settings keep their positions.
ma50_fallback = ta.sma(close, 10)
ma50          = na(ma50_full) ? ma50_fallback : ma50_full

// Intraday: widen the window so this ADR stays comparable to the
// daily-equivalent range used elsewhere in the suite (price_overlay.py,
// rs_ma_distance.py both use the same 2.2x multiplier). Raw intraday bars
// have far smaller high-low ranges than a daily bar, so without this,
// extension_factor below was being scaled by a much smaller, noisier ADR
// than the other panes on the same chart use.
adr_len         = (timeframe.isdaily or timeframe.isweekly) ? adr_length : int(2.2 * adr_length)
adr             = ta.sma(high - low, adr_len)

// Signed distance: positive = above MA50, negative = below
distance_to_ma50 = close - ma50

// How many ADRs away from MA50 the price currently sits.
// Guarded: a zero ADR (halted / no-range bars, common on thin small caps) made
// this ±inf, which blew out the pane autoscale and poisoned every ta.highest /
// ta.lowest below it for the full lookback window.
extension_factor = (not na(adr) and adr != 0) ? distance_to_ma50 / adr : float(na)

// Smoothed extension. Hidden by default (see plot below), but still drives the
// Tier 4 bar colour, so it is computed unconditionally.
extension_ma10  = ta.sma(extension_factor, ma_10_length)

// =============================================================================
// === Extension Extremes ======================================================
// =============================================================================
is_highest_200 = extension_factor == ta.highest(extension_factor, lookback_200)
is_lowest_200  = extension_factor == ta.lowest(extension_factor,  lookback_200)
is_highest_50  = extension_factor == ta.highest(extension_factor, lookback_50)
is_lowest_50   = extension_factor == ta.lowest(extension_factor,  lookback_50)

// =============================================================================
// === Extension Bar Color =====================================================
// =============================================================================
// One palette, driven by SEVERITY only. Direction is not encoded in hue because
// the plot is a signed column around zero — the bar already points up or down,
// so colouring it warm-vs-cool would have restated what the geometry shows.
//
//   C_MAX   200-bar record AND beyond ±7   — the extreme worth stopping on
//   C_REC   200-bar record, within ±7
//   C_BEY   beyond ±7, not a record
//   GREEN   emerging strength — consecutive climb off a low base (see below)
//   RED     emerging weakness — consecutive fall off a high base, mirrors GREEN
//   C_NEAR  50-bar extreme
//   C_ABOVE above the extension 10MA
//   C_DIM   below the extension 10MA
//
// The original cascade also had the two neutral tiers backwards. #ffffffce is
// alpha 0xCE = 81% transparent, while the default was color.new(color.white, 70)
// = 70%. So bars ABOVE the extension 10MA drew FAINTER than bars below it,
// despite the comment claiming "brighter white". Corrected below.
//
// Note: ±high_threshold (±4) is still used only for hlines, not bar colouring.
C_MAX   = #ff2b2b                        // record AND beyond the threshold
C_REC   = #ffd11a                        // 200-bar record
C_BEY   = #ff8a1f                        // beyond the threshold
C_NEAR  = color.new(#ffd11a, 45)         // 50-bar extreme
C_ABOVE = color.new(color.white, 35)     // above extension 10MA
C_DIM   = color.new(color.white, 70)     // below extension 10MA

// Trend-start stages. Green and this red are otherwise unused in this
// palette, so each reads as its own category rather than a shade of the
// severity scale. Fixed 3-stage schedule (not a continuous ramp): day 3 of a
// qualifying streak = light, day 4 = dark, day 5+ = full — matching exactly
// how many consecutive days have confirmed the move.
//
// Downtrend deliberately stops at "dark", never "full" — #ff6b6b stays a
// lighter coral even fully opaque, so an established breakdown streak is
// never the same saturated red as C_MAX, and can't be confused with a
// 200-bar-record-and-beyond-threshold bar.
C_UP_LIGHT   = color.new(#2f9e4f, 55)    // uptrend day 3 — light, translucent green
C_UP_DARK    = color.new(#2f9e4f,  0)    // uptrend day 4 — solid, medium green
C_UP_FULL    = #00ff7f                   // uptrend day 5+ — solid, bright green

C_DOWN_LIGHT = color.new(#ff6b6b, 55)    // downtrend day 3 — light, translucent red
C_DOWN_DARK  = color.new(#ff6b6b,  0)    // downtrend day 4+ — solid coral-red, deliberately short of C_MAX

// Each condition is direction-agnostic: a 200-bar record at either end counts as
// a record, and ±7 counts in both signs.
is_record = is_highest_200 or is_lowest_200
is_beyond = extension_factor > extreme_threshold or extension_factor < -extreme_threshold
is_near   = is_highest_50  or is_lowest_50

// =============================================================================
// === Emerging Strength / Emerging Weakness ===================================
// =============================================================================
// Pattern: extension_factor sets a fresh 50-bar high (or low) for N
// consecutive bars — i.e. dim yellow (is_near) fires N days running in the
// same direction — having STARTED from a near-zero reading. That's price
// reclaiming its 50MA from a washed-out position (strength), or rolling over
// from one before it's gone far (weakness): the early phase of a move,
// before it becomes extended.
//
// Deliberately stricter than "extension_factor > yesterday": every day of
// the streak has to clear the whole trailing 50-bar window, not just the
// prior bar. That makes a green/red streak structurally the same event as
// consecutive dim-yellow days, just counted and colored once it runs 3+ deep
// — so days 1-2 of a streak show dim yellow automatically, with no separate
// handling needed, because is_near is true on those exact days by
// construction.
//
// streak_base records the value the bar before the streak began, not the
// current value, so the "started low" test survives as the streak carries
// price well above zero. Reset is total: one non-qualifying bar clears both
// the count and the base.
var int   rise_count       = 0
var float streak_base      = na
var int   fall_count       = 0
var float fall_streak_base = na

if is_highest_50
    if rise_count == 0
        streak_base := extension_factor[1]   // value the bar before the streak started
    rise_count := rise_count + 1
else
    rise_count  := 0
    streak_base := na

if is_lowest_50
    if fall_count == 0
        fall_streak_base := extension_factor[1]   // value the bar before the streak started
    fall_count := fall_count + 1
else
    fall_count       := 0
    fall_streak_base := na

// "Active" as soon as a streak starts (count >= 1) — the gate only depends
// on streak_base, which is already known from the streak's first bar.
// Combined with the count >= strength_min_days check below to decide
// emerging_strength / emerging_weakness.
up_streak_active   = show_strength and rise_count >= 1 and not na(streak_base)      and streak_base      <= strength_base_max
down_streak_active = show_weakness and fall_count >= 1 and not na(fall_streak_base) and fall_streak_base >= -strength_base_max

emerging_strength = up_streak_active   and rise_count >= strength_min_days
emerging_weakness = down_streak_active and fall_count >= strength_min_days

// Fixed schedule, not a tunable ramp: the 1st qualifying day (rise_count ==
// strength_min_days) = light, the next day = dark, the day after = full
// (uptrend only — downtrend stops at dark, see above). Offsets are relative
// to strength_min_days rather than hardcoded, so this still lines up
// correctly if that input is changed from its default of 3.
strength_color = rise_count >= strength_min_days + 2 ? C_UP_FULL   : rise_count == strength_min_days + 1 ? C_UP_DARK   : C_UP_LIGHT
weakness_color =                                                     fall_count >= strength_min_days + 1 ? C_DOWN_DARK : C_DOWN_LIGHT

color extension_color = C_DIM

// Records are tested before thresholds, and is_highest_200 implies is_highest_50,
// so the 50-bar tier only surfaces when no stronger condition holds.
if is_record and is_beyond
    extension_color := C_MAX
else if is_record
    extension_color := C_REC
else if is_beyond
    extension_color := C_BEY
else if emerging_strength
    extension_color := strength_color
else if emerging_weakness
    extension_color := weakness_color
else if is_near
    extension_color := C_NEAR
else if extension_factor > extension_ma10
    extension_color := C_ABOVE
else
    extension_color := C_DIM

// =============================================================================
// === Plots ===================================================================
// =============================================================================
plot(extension_factor, title="Distance to 50MA / ADR", style=plot.style_columns, color=extension_color)

// Average line off by default — toggle "10MA of Extension Factor" in the
// indicator's Style tab to show it. It still feeds the Tier 4 bar colour.
plot(extension_ma10, title="10MA of Extension Factor", color=#52ffff, linewidth=1, display=display.none)

// Threshold lines lightened so they read as background reference rather than
// competing with the columns for attention.
hline(extreme_threshold,  "Extreme High",  color=color.new(color.red, 80), linewidth=1)
hline(-extreme_threshold, "Extreme Low",   color=color.new(color.red, 80), linewidth=1)
hline(high_threshold,     "High",          color=color.new(#52ff94,   80), linewidth=1)
hline(-high_threshold,    "High Low",      color=color.new(#52ff94,   80), linewidth=1)

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