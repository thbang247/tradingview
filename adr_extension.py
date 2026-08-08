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

// --- VCP ---
vcp_contraction_pct = input.float(0.75, "VCP Contraction Threshold", group="VCP")

// =============================================================================
// === Extension Factor (distance to 50MA, scaled by ADR) ======================
// =============================================================================
ma50            = ta.sma(close, ma_50_length)
adr             = ta.sma(high - low, adr_length)

// Signed distance: positive = above MA50, negative = below
distance_to_ma50 = close - ma50

// How many ADRs away from MA50 the price currently sits
extension_factor = distance_to_ma50 / adr

// Smoothed extension for trend context
extension_ma10  = ta.sma(extension_factor, ma_10_length)

// =============================================================================
// === Extension Extremes ======================================================
// =============================================================================
is_highest_200 = extension_factor == ta.highest(extension_factor, lookback_200)
is_lowest_200  = extension_factor == ta.lowest(extension_factor,  lookback_200)
is_highest_50  = extension_factor == ta.highest(extension_factor, lookback_50)
is_lowest_50   = extension_factor == ta.lowest(extension_factor,  lookback_50)

// =============================================================================
// === Extension Bar Color (4-tier cascade) ====================================
// =============================================================================
// Priority order (highest wins):
//   Tier 1: 200-bar extreme high or low         → red/orange  rgb(255,102,82)
//   Tier 2: beyond ±extreme_threshold (±7)      → bright yellow  #f3ff52
//   Tier 3: 50-bar extreme (but within ±7)      → muted yellow  #f1f36686
//   Tier 4: above extension 10MA                → bright white  #ffffffce
//   Default: below extension 10MA               → dim white
// Note: ±high_threshold (±4) is used only for hlines, not bar coloring.
color extension_color = color.new(color.white, 70)

if is_highest_200 or is_lowest_200
    extension_color := color.rgb(255, 102, 82)    // Tier 1: 200-bar record
else if extension_factor > extreme_threshold or extension_factor < -extreme_threshold
    extension_color := #f3ff52                    // Tier 2: beyond ±7
else if is_highest_50 or is_lowest_50
    extension_color := #f1f36686                  // Tier 3: 50-bar extreme (within ±7)
else if extension_factor > extension_ma10
    extension_color := #ffffffce                  // Tier 4: above 10MA — brighter white
else
    extension_color := color.new(color.white, 70) // Default: dim white

// =============================================================================
// === Plots: Extension ========================================================
// =============================================================================
plot(extension_factor, title="Distance to 50MA / ADR", style=plot.style_columns, color=extension_color)
plot(extension_ma10,   title="10MA of Extension Factor", color=#52ffff, linewidth=1)

hline(extreme_threshold,  "Extreme High",  color=color.new(color.red,   50), linewidth=1)
hline(-extreme_threshold, "Extreme Low",   color=color.new(color.red,   50), linewidth=1)
hline(high_threshold,     "High",          color=#52ff9480,                  linewidth=1)
hline(-high_threshold,    "High Low",      color=#52ff9480,                  linewidth=1)

// =============================================================================
// === VCP Pattern Detection ===================================================
// =============================================================================
// Compares average PERCENTAGE range across four NON-OVERLAPPING, sequential
// time epochs, ordered oldest → newest:
//
//   base   = bars 39..20 back   ta.sma(rng, 20)[20]   pre-consolidation reference
//   mid    = bars 19..10 back   ta.sma(rng, 10)[10]
//   prev   = bars  9..5  back   ta.sma(rng, 5)[5]
//   recent = bars  4..0  back   ta.sma(rng, 5)        current squeeze
//
// Because the windows share no bars, the threshold means exactly what it
// says: each check demands a true (1 - threshold) contraction vs the PRIOR
// epoch, with no self-dilution from nested averages.
//
// Range is normalized by close ((high-low)/close) so contractions register
// correctly even when price has run up substantially over the base.
//
// Checks, in temporal order of the pattern:
//   c3: mid    < base × threshold   (first / outermost contraction)
//   c2: prev   < mid  × threshold   (second contraction)
//   c1: recent < prev × threshold   (final / innermost squeeze)
//
// Count is CASCADE-GATED — later contractions only count if the earlier
// ones in the sequence are intact, enforcing monotonic tightening:
//   1T = c3            (base structure contracting)
//   2T = c3 ∧ c2
//   3T = c3 ∧ c2 ∧ c1  (full progressive squeeze)
//
// Dot hue     = contraction count (1T=orange, 2T=yellow-green, 3T=green)
// Dot opacity = overall tightness (recent/base): brighter = tighter

vcp_rng    = (high - low) / close    // percentage range, price-normalized

vcp_recent = ta.sma(vcp_rng, 5)          // bars 0..4   (newest epoch)
vcp_prev   = ta.sma(vcp_rng, 5)[5]       // bars 5..9
vcp_mid    = ta.sma(vcp_rng, 10)[10]     // bars 10..19
vcp_base   = ta.sma(vcp_rng, 20)[20]     // bars 20..39 (oldest epoch)

// Contraction checks (each epoch vs the one before it in time)
vcp_c3 = vcp_mid    < vcp_base * vcp_contraction_pct
vcp_c2 = vcp_prev   < vcp_mid  * vcp_contraction_pct
vcp_c1 = vcp_recent < vcp_prev * vcp_contraction_pct

// Uptrend prerequisite: price above MA50
vcp_in_trend = close > ma50

// Cascade-gated count: a later contraction only counts if all earlier ones hold
int vcp_count = 0
if vcp_in_trend and vcp_c3
    if vcp_c2
        if vcp_c1
            vcp_count := 3
        else
            vcp_count := 2
    else
        vcp_count := 1

// Tightness: recent as fraction of base (full-pattern squeeze depth)
// Lower ratio = tighter. Alpha clamped to [5, 55] so 1T dots stay visible.
vcp_tightness = vcp_base > 0 ? vcp_recent / vcp_base : 1.0
vcp_alpha     = int(math.min(55, math.max(5, vcp_tightness * 100)))

// Color: orange (1T) → yellow-green (2T) → bright green (3T)
vcp_dot_color = vcp_count == 3 ? color.new(color.rgb(0,   255, 80),  vcp_alpha) : vcp_count == 2 ? color.new(color.rgb(180, 255, 0),  vcp_alpha) : vcp_count == 1 ? color.new(color.rgb(255, 140, 0),  vcp_alpha) : na

// === VCP Signal Dot ==========================================================
// Sits just below -extreme_threshold hline so it never overlaps extension bars
plot(vcp_count > 0 ? -extreme_threshold - 1 : na, style=plot.style_circles, color=vcp_dot_color, linewidth=2, title="VCP Pattern")

// === VCP Diagnostic Ratios ===================================================
// Raw ratio at each contraction stage, in temporal order (c3 → c2 → c1).
// A stage is active when its ratio is below the threshold (default 0.75).
// Enable in chart settings to debug which stages are triggering.
plot(vcp_mid    / vcp_base, title="VCP Ratio c3 (mid/base)",    color=color.new(color.lime,   60), linewidth=1, display=display.none)
plot(vcp_prev   / vcp_mid,  title="VCP Ratio c2 (prev/mid)",    color=color.new(color.yellow, 60), linewidth=1, display=display.none)
plot(vcp_recent / vcp_prev, title="VCP Ratio c1 (recent/prev)", color=color.new(color.orange, 60), linewidth=1, display=display.none)

// =============================================================================
// === Background: NDFD Market Condition =======================================
// =============================================================================
daily_close_ndfd = request.security("NDFD", "D", close)
var color bg_color = na

if timeframe.isintraday or timeframe.isdaily
    if daily_close_ndfd < 10
        bg_color := color.new(color.green, 90)
    else if daily_close_ndfd > 85
        bg_color := color.new(color.red, 90)
    else
        bg_color := na
else
    bg_color := na

bgcolor(bg_color)