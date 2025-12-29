#!/bin/bash
# PFLOTRAN Performance Monitor - Optimized for 13th Gen Intel hybrid architecture
# Based on successful diagnostic results

OUTPUT_DIR="./pflotran_perf_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "PFLOTRAN Performance Monitor (13th Gen Intel Optimized)"
echo "======================================================="
echo "CPU: 13th Gen Intel i5-13600K (Hybrid P+E cores)"
echo "Output directory: $OUTPUT_DIR"
echo "Timestamp: $(date)"
echo ""

# Verified working events from diagnostic
PERF_EVENTS="cache-misses,cache-references,instructions,cycles"

# Also test for additional Intel-specific events
echo "Testing additional Intel-specific events..."
EXTENDED_EVENTS=""

# Test for Intel-specific events that might work
intel_events="branches branch-misses L1-dcache-loads L1-dcache-load-misses LLC-loads LLC-load-misses"
for event in $intel_events; do
    if perf stat -e "$event" true >/dev/null 2>&1; then
        EXTENDED_EVENTS="${EXTENDED_EVENTS:+$EXTENDED_EVENTS,}$event"
        echo "✓ $event available"
    else
        echo "✗ $event not available"
    fi
done

# Combine working events
if [ -n "$EXTENDED_EVENTS" ]; then
    ALL_EVENTS="$PERF_EVENTS,$EXTENDED_EVENTS"
else
    ALL_EVENTS="$PERF_EVENTS"
fi

echo "Using events: $ALL_EVENTS"
echo ""

# Function to cleanup background processes
cleanup() {
    echo "Stopping monitoring..."
    jobs -p | xargs -r kill 2>/dev/null
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# Start background monitoring
echo "Starting system monitoring..."

# Memory monitoring
(while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $(free -h | grep '^Mem:')" >> "$OUTPUT_DIR/memory.log"
    sleep 5
done) &

# I/O monitoring
iostat -x 2 > "$OUTPUT_DIR/iostat.log" &

# CPU monitoring with detailed breakdown
vmstat 2 > "$OUTPUT_DIR/vmstat.log" &

# Core-specific monitoring for hybrid architecture
(while true; do
    echo "=== $(date) ===" >> "$OUTPUT_DIR/cpu_usage.log"
    # Monitor per-core usage (useful for hybrid P+E core analysis)
    if command -v mpstat >/dev/null 2>&1; then
        mpstat -P ALL 1 1 >> "$OUTPUT_DIR/cpu_usage.log" 2>/dev/null
    fi
    sleep 10
done) &

echo "Background monitoring started."
echo ""

# Run PFLOTRAN with perf monitoring
echo "Starting PFLOTRAN with performance monitoring..."
echo "Command: $@"
echo ""

# Use the verified working perf command format
echo "Executing: perf stat -e \"$ALL_EVENTS\" --output \"$OUTPUT_DIR/perf_raw.log\" $@"

perf stat \
    -e "$ALL_EVENTS" \
    --output "$OUTPUT_DIR/perf_raw.log" \
    "$@"

PFLOTRAN_EXIT=$?
echo ""
echo "PFLOTRAN completed with exit code: $PFLOTRAN_EXIT"

# Parse and analyze results
echo "Analyzing performance data..."

# Create analysis script optimized for 13th Gen Intel
cat > "$OUTPUT_DIR/analyze_intel_hybrid.py" << 'EOF'
#!/usr/bin/env python3
import re
import sys

def parse_intel_hybrid_perf(filename):
    """Parse perf output from Intel 13th gen hybrid architecture"""
    metrics = {}
    
    try:
        with open(filename, 'r') as f:
            content = f.read()
        
        # Intel 13th gen shows separate counters for P-cores (cpu_core) and E-cores (cpu_atom)
        patterns = {
            'p_core_cache_misses': r'(\d+(?:,\d+)*)\s+cpu_core/cache-misses/',
            'e_core_cache_misses': r'(\d+(?:,\d+)*)\s+cpu_atom/cache-misses/',
            'p_core_cache_refs': r'(\d+(?:,\d+)*)\s+cpu_core/cache-references/',
            'e_core_cache_refs': r'(\d+(?:,\d+)*)\s+cpu_atom/cache-references/',
            'p_core_instructions': r'(\d+(?:,\d+)*)\s+cpu_core/instructions/',
            'e_core_instructions': r'(\d+(?:,\d+)*)\s+cpu_atom/instructions/',
            'p_core_cycles': r'(\d+(?:,\d+)*)\s+cpu_core/cycles/',
            'e_core_cycles': r'(\d+(?:,\d+)*)\s+cpu_atom/cycles/',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match and 'not counted' not in match.group(0):
                value = int(match.group(1).replace(',', ''))
                metrics[key] = value
        
        # Also look for combined metrics (when not split by core type)
        combined_patterns = {
            'total_cache_misses': r'(\d+(?:,\d+)*)\s+cache-misses',
            'total_cache_refs': r'(\d+(?:,\d+)*)\s+cache-references',
            'total_instructions': r'(\d+(?:,\d+)*)\s+instructions',
            'total_cycles': r'(\d+(?:,\d+)*)\s+cycles',
        }
        
        for key, pattern in combined_patterns.items():
            matches = re.findall(pattern, content)
            if matches:
                # Sum all matches (in case there are multiple entries)
                total = sum(int(match.replace(',', '')) for match in matches)
                metrics[key] = total
        
        # Extract timing
        time_match = re.search(r'(\d+\.?\d*)\s+seconds time elapsed', content)
        if time_match:
            metrics['elapsed_time'] = float(time_match.group(1))
            
    except Exception as e:
        print(f"Error parsing perf output: {e}")
    
    return metrics

def analyze_hybrid_performance(metrics):
    """Analyze performance for Intel hybrid architecture"""
    analysis = []
    
    analysis.append("Intel 13th Gen Hybrid Architecture Performance Analysis")
    analysis.append("=" * 55)
    analysis.append("")
    
    # Hybrid core analysis
    p_core_active = any(key.startswith('p_core_') for key in metrics.keys() if metrics.get(key, 0) > 0)
    e_core_active = any(key.startswith('e_core_') for key in metrics.keys() if metrics.get(key, 0) > 0)
    
    analysis.append("Core Type Utilization:")
    analysis.append(f"  P-cores (Performance): {'✓ Active' if p_core_active else '✗ Inactive'}")
    analysis.append(f"  E-cores (Efficiency):  {'✓ Active' if e_core_active else '✗ Inactive'}")
    analysis.append("")
    
    # Calculate combined metrics
    total_cache_misses = 0
    total_cache_refs = 0
    total_instructions = 0
    total_cycles = 0
    
    # Sum P-core and E-core metrics
    for core_type in ['p_core_', 'e_core_']:
        total_cache_misses += metrics.get(f'{core_type}cache_misses', 0)
        total_cache_refs += metrics.get(f'{core_type}cache_refs', 0)
        total_instructions += metrics.get(f'{core_type}instructions', 0)
        total_cycles += metrics.get(f'{core_type}cycles', 0)
    
    # Use total metrics if available, otherwise use calculated sums
    if 'total_cache_misses' in metrics:
        total_cache_misses = metrics['total_cache_misses']
    if 'total_cache_refs' in metrics:
        total_cache_refs = metrics['total_cache_refs']
    if 'total_instructions' in metrics:
        total_instructions = metrics['total_instructions']
    if 'total_cycles' in metrics:
        total_cycles = metrics['total_cycles']
    
    # Cache analysis with accurate thresholds
    cache_miss_ratio = 0
    if total_cache_refs > 0:
        cache_miss_ratio = total_cache_misses / total_cache_refs
        analysis.append("Cache Performance (Combined P+E cores):")
        analysis.append(f"  Cache misses: {total_cache_misses:,}")
        analysis.append(f"  Cache references: {total_cache_refs:,}")
        analysis.append(f"  Cache miss ratio: {cache_miss_ratio*100:.2f}%")
        
        if cache_miss_ratio > 0.80:
            analysis.append("  🔴 CRITICAL - Extreme cache miss rate indicates severe memory bandwidth bottleneck")
        elif cache_miss_ratio > 0.50:
            analysis.append("  🔴 SEVERE - Very high cache miss rate indicates major memory bandwidth bottleneck")
        elif cache_miss_ratio > 0.25:
            analysis.append("  ✗ POOR - High cache miss rate indicates memory bandwidth bottleneck")
        elif cache_miss_ratio > 0.15:
            analysis.append("  ⚠ FAIR - Elevated cache miss rate, moderate memory pressure")
        elif cache_miss_ratio > 0.10:
            analysis.append("  ⚠ BORDERLINE - Slightly elevated cache miss rate")
        elif cache_miss_ratio > 0.05:
            analysis.append("  ✓ GOOD - Acceptable cache performance")
        else:
            analysis.append("  ✓ EXCELLENT - Very efficient cache usage")
    
    analysis.append("")
    
    # CPU efficiency
    ipc = 0
    if total_cycles > 0:
        ipc = total_instructions / total_cycles
        analysis.append("CPU Efficiency (Combined P+E cores):")
        analysis.append(f"  Instructions: {total_instructions:,}")
        analysis.append(f"  Cycles: {total_cycles:,}")
        analysis.append(f"  Instructions per cycle: {ipc:.2f}")
        
        if ipc > 2.0:
            analysis.append("  ✓ EXCELLENT - High computational efficiency")
        elif ipc > 1.0:
            analysis.append("  ✓ GOOD - Decent CPU utilization")
        elif ipc > 0.5:
            analysis.append("  ⚠ FAIR - CPU waiting on memory/I-O")
        else:
            analysis.append("  ✗ POOR - CPU severely underutilized")
    
    analysis.append("")
    
    # Per-core type analysis (if data available)
    if p_core_active and e_core_active:
        analysis.append("Per-Core Type Analysis:")
        
        # P-core efficiency
        p_instructions = metrics.get('p_core_instructions', 0)
        p_cycles = metrics.get('p_core_cycles', 0)
        if p_cycles > 0:
            p_ipc = p_instructions / p_cycles
            analysis.append(f"  P-cores IPC: {p_ipc:.2f}")
        
        # E-core efficiency  
        e_instructions = metrics.get('e_core_instructions', 0)
        e_cycles = metrics.get('e_core_cycles', 0)
        if e_cycles > 0:
            e_ipc = e_instructions / e_cycles
            analysis.append(f"  E-cores IPC: {e_ipc:.2f}")
        
        # Workload distribution
        if p_instructions > 0 and e_instructions > 0:
            total_work = p_instructions + e_instructions
            p_percentage = (p_instructions / total_work) * 100
            analysis.append(f"  Workload distribution: {p_percentage:.1f}% P-cores, {100-p_percentage:.1f}% E-cores")
    
    analysis.append("")
    
    # Memory bandwidth impact calculation
    if total_cache_refs > 0 and cache_miss_ratio > 0.5:
        analysis.append("Memory Bandwidth Impact Analysis:")
        analysis.append(f"  With {cache_miss_ratio*100:.1f}% cache miss rate:")
        
        # DDR4-3200 penalty: ~300 cycles, DDR5-5600 penalty: ~180 cycles
        ddr4_avg_cycles = (cache_miss_ratio * 300) + ((1 - cache_miss_ratio) * 3)
        ddr5_avg_cycles = (cache_miss_ratio * 180) + ((1 - cache_miss_ratio) * 3)
        improvement_factor = ddr4_avg_cycles / ddr5_avg_cycles
        
        analysis.append(f"  Current DDR4-3200: ~{ddr4_avg_cycles:.0f} cycles average per memory access")
        analysis.append(f"  With DDR5-5600: ~{ddr5_avg_cycles:.0f} cycles average per memory access")
        analysis.append(f"  Expected improvement: {improvement_factor:.1f}x faster with DDR5 upgrade")
        analysis.append("")
    
    # Overall assessment with accurate severity detection
    analysis.append("PFLOTRAN Performance Assessment:")
    analysis.append("-" * 35)
    
    # Determine severity based on cache miss ratio primarily
    if cache_miss_ratio > 0.70:
        analysis.append("🔴 SEVERE MEMORY BANDWIDTH BOTTLENECK")
        analysis.append("   Cache miss ratio of {:.1f}% indicates critical memory bandwidth saturation".format(cache_miss_ratio*100))
        analysis.append("   DDR4-3200 is completely insufficient for PFLOTRAN's memory access patterns")
        analysis.append("   Immediate upgrade to DDR5-5600+ recommended for substantial performance gains")
        analysis.append("   Expected improvement: 60-80% faster simulation times")
        analysis.append("")
        analysis.append("   Performance Impact:")
        analysis.append("   - CPU spends most time waiting for memory (~{:.0f} cycles per access)".format((cache_miss_ratio * 300) + ((1 - cache_miss_ratio) * 3)))
        analysis.append("   - Sparse matrix operations severely bottlenecked")
        analysis.append("   - Storage optimization is secondary until memory bandwidth is addressed")
    elif cache_miss_ratio > 0.40:
        analysis.append("🔴 MAJOR MEMORY BANDWIDTH BOTTLENECK")
        analysis.append("   Cache miss ratio of {:.1f}% indicates significant memory bandwidth limitations".format(cache_miss_ratio*100))
        analysis.append("   DDR4-3200 memory bandwidth is insufficient for optimal PFLOTRAN performance")
        analysis.append("   Strong recommendation: Upgrade to DDR5-5600+ for major performance gains")
        analysis.append("   Expected improvement: 40-60% faster simulation times")
    elif cache_miss_ratio > 0.20:
        analysis.append("🟡 MODERATE MEMORY BANDWIDTH BOTTLENECK")
        analysis.append("   Cache miss ratio of {:.1f}% indicates notable memory bandwidth pressure".format(cache_miss_ratio*100))
        analysis.append("   DDR4-3200 memory is limiting performance but not critically")
        analysis.append("   Recommendation: Consider DDR5 upgrade for 20-40% performance improvement")
    elif cache_miss_ratio > 0.12:
        analysis.append("🟡 MILD MEMORY PRESSURE")
        analysis.append("   Cache miss ratio of {:.1f}% shows some memory bandwidth limitations".format(cache_miss_ratio*100))
        analysis.append("   Current memory setup is adequate but could benefit from faster memory")
    else:
        analysis.append("🟢 GOOD MEMORY PERFORMANCE")
        analysis.append("   Cache miss ratio of {:.1f}% indicates efficient memory usage".format(cache_miss_ratio*100))
        analysis.append("   No obvious memory bandwidth bottlenecks detected")
        analysis.append("   System appears well-balanced for current PFLOTRAN workload")
    
    return "\n".join(analysis)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 analyze_intel_hybrid.py <perf_raw.log>")
        sys.exit(1)
    
    filename = sys.argv[1]
    metrics = parse_intel_hybrid_perf(filename)
    analysis = analyze_hybrid_performance(metrics)
    
    print(analysis)
    print("\nRaw Metrics:")
    print("-" * 12)
    for key, value in sorted(metrics.items()):
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value:,}")
EOF

# Run the analysis
if [ -f "$OUTPUT_DIR/perf_raw.log" ]; then
    python3 "$OUTPUT_DIR/analyze_intel_hybrid.py" "$OUTPUT_DIR/perf_raw.log" > "$OUTPUT_DIR/performance_analysis.txt"
    echo "✓ Performance analysis complete"
else
    echo "⚠ No perf data found"
fi

# Memory analysis
if [ -f "$OUTPUT_DIR/memory.log" ]; then
    echo "Analyzing memory usage..."
    START_MEM=$(head -n1 "$OUTPUT_DIR/memory.log" | grep -o '[0-9.]*Gi' | head -1 | sed 's/Gi//')
    END_MEM=$(tail -n1 "$OUTPUT_DIR/memory.log" | grep -o '[0-9.]*Gi' | head -1 | sed 's/Gi//')
    PEAK_MEM=$(grep -o '[0-9.]*Gi' "$OUTPUT_DIR/memory.log" | sed 's/Gi//' | sort -n | tail -1)
    
    echo "Memory usage: Start=${START_MEM}GB, End=${END_MEM}GB, Peak=${PEAK_MEM}GB" > "$OUTPUT_DIR/memory_summary.txt"
fi

# I/O analysis
if [ -f "$OUTPUT_DIR/iostat.log" ]; then
    echo "Analyzing storage performance..."
    PEAK_UTIL=$(awk '/^nvme/ {print $7}' "$OUTPUT_DIR/iostat.log" | grep -E '^[0-9]' | sort -n | tail -1)
    HIGH_UTIL_COUNT=$(awk '/^nvme/ {if($7>80) count++} END {print count+0}' "$OUTPUT_DIR/iostat.log")
    
    echo "Storage: Peak utilization=${PEAK_UTIL}%, High utilization periods=${HIGH_UTIL_COUNT}" > "$OUTPUT_DIR/storage_summary.txt"
fi

# Generate final report
cat > "$OUTPUT_DIR/final_report.txt" << EOF
PFLOTRAN Performance Analysis Summary
===================================
Generated: $(date)
System: Intel 13th Gen i5-13600K (P+E core hybrid)
Command: $@
Exit Code: $PFLOTRAN_EXIT

Files Generated:
===============
- performance_analysis.txt: Main performance analysis (START HERE)
- perf_raw.log: Raw perf performance data
- memory.log: Memory usage over time
- iostat.log: Storage I/O statistics
- vmstat.log: System resource usage
- memory_summary.txt: Memory usage summary
- storage_summary.txt: Storage performance summary

Quick Commands:
==============
View main analysis:     cat $OUTPUT_DIR/performance_analysis.txt
Check memory usage:     cat $OUTPUT_DIR/memory_summary.txt  
Check storage performance: cat $OUTPUT_DIR/storage_summary.txt
View raw perf data:     cat $OUTPUT_DIR/perf_raw.log
EOF

echo ""
echo "=============================================="
echo "Performance Monitoring Complete!"
echo "=============================================="

# Display quick results
if [ -f "$OUTPUT_DIR/performance_analysis.txt" ]; then
    echo ""
    echo "Performance Analysis Preview:"
    echo "============================="
    head -n 25 "$OUTPUT_DIR/performance_analysis.txt"
    echo ""
    echo "(Full analysis in: $OUTPUT_DIR/performance_analysis.txt)"
fi

echo ""
echo "Key files:"
echo "- Main analysis: $OUTPUT_DIR/performance_analysis.txt"
echo "- Summary report: $OUTPUT_DIR/final_report.txt"
echo "- Raw perf data: $OUTPUT_DIR/perf_raw.log"
echo ""
echo "Quick check commands:"
echo "cat $OUTPUT_DIR/performance_analysis.txt"
echo "cat $OUTPUT_DIR/memory_summary.txt"
echo "cat $OUTPUT_DIR/storage_summary.txt"
