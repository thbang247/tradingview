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
lookback_200            = input.int(200, "Extreme Lookback (long)",  group="Thresholds")
lookback_50             = input.int(50,  "Extreme Lookback (short)", group="Thresholds")

// --- Emerging strength ---
// Appended at the end of the input list so existing saved settings keep their
// positions.
show_strength      = input.bool(true, "Highlight Emerging Strength",              group="Emerging Strength")
strength_min_days  = input.int(3,   "Consecutive Rising Bars", minval=2,          group="Emerging Strength")
strength_base_max  = input.float(1.0, "Max Extension Where Streak Began (ADR)",   group="Emerging Strength")
strength_ramp_bars = input.int(5,   "Extra Bars To Full Green", minval=1,         group="Emerging Strength")

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

adr             = ta.sma(high - low, adr_length)

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
//   C_NEAR  50-bar extreme (early warning)
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
C_REC   = #ff8a1f                        // 200-bar record
C_BEY   = #ffd11a                        // beyond the threshold
C_NEAR  = color.new(#ffd11a, 45)         // 50-bar extreme
C_ABOVE = color.new(color.white, 35)     // above extension 10MA
C_DIM   = color.new(color.white, 70)     // below extension 10MA

// Emerging-strength ramp. Green is otherwise unused in this palette, so it reads
// as its own category rather than a shade of the severity scale.
//
// The ramp moves on BOTH axes — colour.from_gradient interpolates transparency
// along with RGB, so the streak starts as a dim, translucent green barely louder
// than the neutral tiers and only becomes solid bright green once it has run. A
// three-bar streak is weak evidence and should look like it; the brightness is
// what separates "something may be starting" from "this is under way".
C_STR_LOW = color.new(#2f9e4f, 55)       // streak just qualified — dim, translucent
C_STR_HI  = color.new(#00ff7f,  0)       // streak well established — solid, bright

// Each condition is direction-agnostic: a 200-bar record at either end counts as
// a record, and ±7 counts in both signs.
is_record = is_highest_200 or is_lowest_200
is_beyond = extension_factor > extreme_threshold or extension_factor < -extreme_threshold
is_near   = is_highest_50  or is_lowest_50

// =============================================================================
// === Emerging Strength =======================================================
// =============================================================================
// Pattern: the extension climbs for N consecutive bars, having STARTED from a
// negative or near-zero reading. That is price reclaiming its 50MA from a washed
// out or flat position — the early phase of a move, before it becomes extended.
//
// Without this, those bars land in C_NEAR (muted amber, "50-bar extreme") or the
// neutral whites, which say how unusual the reading is but nothing about which
// way it is travelling. A recovery therefore looked identical to a breakdown.
//
// streak_base records where the climb began, not the current value, so the
// "started low" test survives as the streak carries price well above zero.
// Reset is total: one non-rising bar clears both the count and the base.
rising = not na(extension_factor) and not na(extension_factor[1]) and extension_factor > extension_factor[1]

var int   rise_count  = 0
var float streak_base = na

if rising
    if rise_count == 0
        streak_base := extension_factor[1]   // value the bar before the climb started
    rise_count := rise_count + 1
else
    rise_count  := 0
    streak_base := na

emerging_strength = show_strength and rise_count >= strength_min_days and not na(streak_base) and streak_base <= strength_base_max

// Intensity ramps with streak length: dim translucent green on the bar it
// qualifies (3 by default), brightening one step per additional consecutive bar
// and reaching solid green strength_ramp_bars later — 8 bars on the defaults.
// Clamped, so it stops brightening past the top rather than saturating early.
strength_top   = strength_min_days + strength_ramp_bars
strength_color = color.from_gradient(math.min(rise_count, strength_top), strength_min_days, strength_top, C_STR_LOW, C_STR_HI)

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