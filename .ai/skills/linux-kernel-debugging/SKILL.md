---
name: linux-kernel-debugging
description: Expert-level Linux kernel development and debugging techniques. Use when debugging kernel issues, kernel panics, driver problems, memory corruption, race conditions, or any kernel-level development work.
---

# Linux Kernel Development & Debugging

Expert-level debugging techniques for Linux kernel development, driver debugging, and kernel internals analysis.

## When to Use This Skill
- Debugging kernel panics, oops, or BUG() assertions
- Analyzing memory corruption issues
- Debugging race conditions and deadlocks
- Driver development and debugging
- Performance analysis at kernel level
- Understanding kernel subsystem behavior
- Tracing kernel execution flow

## Core Debugging Tools

### 1. printk Debugging
```c
// Log levels (include/linux/kern_levels.h)
printk(KERN_EMERG   "Emergency: %s\n", msg);   // 0 - System unusable
printk(KERN_ALERT   "Alert: %s\n", msg);       // 1 - Immediate action needed
printk(KERN_CRIT    "Critical: %s\n", msg);    // 2 - Critical conditions
printk(KERN_ERR     "Error: %s\n", msg);       // 3 - Error conditions
printk(KERN_WARNING "Warning: %s\n", msg);     // 4 - Warning conditions
printk(KERN_NOTICE  "Notice: %s\n", msg);      // 5 - Normal but significant
printk(KERN_INFO    "Info: %s\n", msg);        // 6 - Informational
printk(KERN_DEBUG   "Debug: %s\n", msg);       // 7 - Debug messages

// Modern alternatives
pr_err("Error: %s\n", msg);
pr_info("Info: %s\n", msg);
pr_debug("Debug: %s\n", msg);

// Device-specific
dev_err(dev, "Device error: %s\n", msg);
dev_info(dev, "Device info: %s\n", msg);
dev_dbg(dev, "Device debug: %s\n", msg);
```

### 2. Dynamic Debug
```bash
# Enable debug messages dynamically
echo 'file drivers/usb/*.c +p' > /sys/kernel/debug/dynamic_debug/control
echo 'module e1000e +p' > /sys/kernel/debug/dynamic_debug/control
echo 'func kobject_* +p' > /sys/kernel/debug/dynamic_debug/control

# Disable
echo 'file drivers/usb/*.c -p' > /sys/kernel/debug/dynamic_debug/control
```

### 3. ftrace - Function Tracer
```bash
# Basic function tracing
cd /sys/kernel/debug/tracing
echo function > current_tracer
echo 1 > tracing_on
cat trace

# Function graph tracer
echo function_graph > current_tracer
echo vfs_read > set_graph_function
echo 1 > tracing_on

# Filter specific functions
echo 'sys_*' > set_ftrace_filter
echo '!sys_exit' >> set_ftrace_filter

# Trace events
echo 1 > events/sched/sched_switch/enable
echo 1 > events/irq/enable
```

### 4. perf - Performance Analysis
```bash
# CPU profiling
perf top
perf record -g -a sleep 10
perf report

# Specific events
perf stat -e cache-misses,cache-references ./program
perf record -e page-faults -g ./program

# Kernel functions
perf probe --add 'do_sys_open filename:string'
perf record -e probe:do_sys_open -a sleep 5
perf script
```

### 5. BPF/eBPF Tools
```bash
# Using bpftrace
bpftrace -e 'kprobe:do_sys_open { printf("%s\n", str(arg1)); }'
bpftrace -e 'tracepoint:syscalls:sys_enter_read { @[comm] = count(); }'
bpftrace -e 'kretprobe:vfs_read { @bytes = hist(retval); }'

# BCC tools
execsnoop         # Trace new processes
opensnoop         # Trace file opens
biolatency        # Block I/O latency histogram
tcpconnect        # Trace TCP connections
runqlat           # Run queue latency
```

## Analyzing Kernel Crashes

### Decoding Oops/Panic
```bash
# Decode stack trace
./scripts/decode_stacktrace.sh vmlinux < oops.txt

# Decode function+offset
./scripts/faddr2line vmlinux module_function+0x123/0x456

# Using addr2line
addr2line -e vmlinux -f ffffffff81234567

# GDB for symbol lookup
gdb vmlinux
(gdb) list *0xffffffff81234567
```

### Kernel Oops Analysis
```
BUG: unable to handle kernel NULL pointer dereference at 0000000000000010
IP: [<ffffffff81234567>] my_function+0x42/0x100 [my_module]
PGD 0
Oops: 0000 [#1] SMP
```

**Key fields:**
- **IP**: Instruction pointer - where crash occurred
- **Oops code**: 0000 = read, 0002 = write, 0010 = user mode
- **[#1]**: First oops (kernel may become unstable after)
- **Call Trace**: Stack backtrace

### KASAN - Kernel Address Sanitizer
```bash
# Enable in config
CONFIG_KASAN=y
CONFIG_KASAN_GENERIC=y

# Reports use-after-free, out-of-bounds, etc.
# Example output:
# BUG: KASAN: use-after-free in my_function+0x42/0x100
# Read of size 8 at addr ffff8881234567 by task my_task/1234
```

### UBSAN - Undefined Behavior Sanitizer
```bash
CONFIG_UBSAN=y
CONFIG_UBSAN_SANITIZE_ALL=y
```

### KCSAN - Kernel Concurrency Sanitizer
```bash
CONFIG_KCSAN=y
# Detects data races
```

## Memory Debugging

### SLUB Debug
```bash
# Boot options
slub_debug=FZPU

# F - Sanity checks (expensive)
# Z - Red zoning (detect out-of-bounds)
# P - Poisoning (detect use-after-free)
# U - User tracking (track allocations)

# Per-cache debugging
echo 1 > /sys/kernel/slab/kmalloc-256/sanity_checks
```

### Kmemleak
```bash
CONFIG_DEBUG_KMEMLEAK=y

# Scan for leaks
echo scan > /sys/kernel/debug/kmemleak
cat /sys/kernel/debug/kmemleak

# Clear false positives
echo clear > /sys/kernel/debug/kmemleak
```

### Memory Allocation Tracking
```c
// Add tracking to allocations
void *ptr = kzalloc(size, GFP_KERNEL);
if (!ptr)
    return -ENOMEM;

// Check /proc/meminfo
// Check /proc/slabinfo
// Use slabtop for real-time monitoring
```

### Stack Debugging
```bash
# Kernel stack overflow detection
CONFIG_VMAP_STACK=y              # Virtual mapped kernel stacks
CONFIG_DEBUG_STACK_USAGE=y       # Track stack usage
CONFIG_STACK_VALIDATION=y        # Compile-time stack validation

# Check stack usage per process
cat /proc/<pid>/stack            # Process kernel stack trace
cat /proc/<pid>/status | grep Stack  # Stack usage info

# SysRq stack dump
echo t > /proc/sysrq-trigger     # Dump all task stacks
```

```c
// Stack usage checking in code
#include <linux/sched/debug.h>

void check_stack(void) {
    unsigned long stack_left = stack_not_used(current);
    pr_info("Stack remaining: %lu bytes\n", stack_left);
    
    // Trigger warning if stack low
    WARN_ON(stack_left < 1024);
}

// Dump current stack
dump_stack();  // Print current kernel stack
show_stack(current, NULL, KERN_ERR);  // Detailed stack dump
```

### Memory Layout Analysis
```bash
# Kernel memory layout
cat /proc/iomem                   # Physical memory map
cat /proc/vmallocinfo             # vmalloc allocations
cat /sys/kernel/debug/page_owner  # Page allocation tracking

# Enable page owner tracking
CONFIG_PAGE_OWNER=y
page_owner=on                     # Boot parameter

# Analyze page owner
cat /sys/kernel/debug/page_owner | sort | uniq -c | sort -rn
```

```c
// Virtual address space regions (x86_64)
// User space:      0x0000000000000000 - 0x00007FFFFFFFFFFF
// Kernel space:    0xFFFF800000000000 - 0xFFFFFFFFFFFFFFFF
//   Direct mapping: ffff888000000000 - ffffc87fffffffff
//   vmalloc:        ffffc90000000000 - ffffe8ffffffffff
//   vmemmap:        ffffea0000000000 - ffffeaffffffffff
//   Kernel text:    ffffffff80000000 - ffffffff9fffffff
//   Modules:        ffffffffa0000000 - fffffffffdffffff

// Check if address is valid
#include <linux/uaccess.h>
if (access_ok(user_ptr, size)) {
    // Safe to access user pointer
}

// Kernel address validation
#include <linux/mm.h>
if (virt_addr_valid(ptr)) {
    // Valid kernel virtual address
}
```

### Page Table Walking
```c
#include <linux/mm.h>
#include <asm/pgtable.h>

// Walk page tables to debug address translation
void debug_page_tables(struct mm_struct *mm, unsigned long addr) {
    pgd_t *pgd;
    p4d_t *p4d;
    pud_t *pud;
    pmd_t *pmd;
    pte_t *pte;
    
    pgd = pgd_offset(mm, addr);
    if (pgd_none(*pgd) || pgd_bad(*pgd)) {
        pr_err("Bad PGD\n");
        return;
    }
    
    p4d = p4d_offset(pgd, addr);
    pud = pud_offset(p4d, addr);
    pmd = pmd_offset(pud, addr);
    pte = pte_offset_kernel(pmd, addr);
    
    pr_info("addr=0x%lx: pgd=%lx pud=%lx pmd=%lx pte=%lx\n",
            addr, pgd_val(*pgd), pud_val(*pud),
            pmd_val(*pmd), pte_val(*pte));
}
```

### Crash Dump Analysis (kdump)
```bash
# Setup kdump
CONFIG_KEXEC=y
CONFIG_CRASH_DUMP=y

# Install kdump tools
apt install kdump-tools      # Debian/Ubuntu
yum install kexec-tools      # RHEL/CentOS

# Analyze crash dump with crash utility
crash /usr/lib/debug/boot/vmlinux-$(uname -r) /var/crash/vmcore

# crash commands
crash> bt              # Backtrace of crashed task
crash> log             # Kernel log buffer
crash> ps              # Process list at crash time
crash> vm              # Virtual memory info
crash> kmem -s         # SLAB cache info
crash> files           # Open files
crash> rd <addr> 100   # Read memory
crash> dis <func>      # Disassemble function
```


## Lock Debugging

### Lockdep - Lock Dependency Validator
```bash
CONFIG_LOCKDEP=y
CONFIG_PROVE_LOCKING=y
CONFIG_DEBUG_LOCK_ALLOC=y

# Detects:
# - ABBA deadlocks
# - Lock ordering violations
# - Recursive locking issues
# - IRQ-unsafe locking
```

### Lock Statistics
```bash
CONFIG_LOCK_STAT=y

# View stats
cat /proc/lock_stat
```

### Common Lock Issues
```c
// Issue: Sleeping in atomic context
spin_lock(&lock);
kmalloc(size, GFP_KERNEL);  // BUG! Use GFP_ATOMIC
spin_unlock(&lock);

// Issue: Lock ordering
// Task A: lock(&a); lock(&b);
// Task B: lock(&b); lock(&a);  // DEADLOCK!

// Solution: Always acquire locks in consistent order
```

## Debugging with KGDB/KDB

### KGDB Setup
```bash
# Kernel config
CONFIG_KGDB=y
CONFIG_KGDB_SERIAL_CONSOLE=y

# Boot parameters
kgdboc=ttyS0,115200 kgdbwait

# Connect with GDB
gdb vmlinux
(gdb) target remote /dev/ttyS0
(gdb) break my_function
(gdb) continue
```

### KDB Commands
```
kdb> bt          # Backtrace
kdb> ps          # Process list
kdb> lsmod       # Module list
kdb> md <addr>   # Memory dump
kdb> go          # Continue execution
kdb> bp <func>   # Set breakpoint
```

## Driver Debugging

### Device Tree Issues
```bash
# View device tree
dtc -I fs /sys/firmware/devicetree/base

# Check device binding
cat /sys/bus/platform/drivers/my_driver/bind
cat /sys/bus/platform/drivers/my_driver/unbind
```

### DMA Debugging
```bash
CONFIG_DMA_API_DEBUG=y

# Check for DMA errors
dmesg | grep -i dma
cat /sys/kernel/debug/dma-api/errors
```

### I/O Memory Access
```c
// Proper I/O access
void __iomem *base = ioremap(phys_addr, size);
u32 val = readl(base + OFFSET);
writel(val, base + OFFSET);
iounmap(base);

// Debug I/O
pr_debug("REG[0x%x] = 0x%08x\n", OFFSET, readl(base + OFFSET));
```

## Race Condition Detection

### Strategy
1. **Add delays**: Insert `msleep()` or `udelay()` at suspected race points
2. **Stress testing**: Run concurrent operations
3. **Use KCSAN**: Enable kernel concurrency sanitizer
4. **Add assertions**: Use `WARN_ON()` for invariant checks

```c
// Debugging race with intentional delay
spin_lock(&lock);
if (DEBUG_RACE)
    msleep(100);  // Force timing window
// critical section
spin_unlock(&lock);
```

### RCU Debugging
```bash
CONFIG_RCU_CPU_STALL_TIMEOUT=21
CONFIG_RCU_TRACE=y
CONFIG_PROVE_RCU=y

# Check RCU state
cat /sys/kernel/debug/rcu/rcu_preempt/rcudata
```

## Kernel Build for Debugging
```bash
# Essential debug configs
CONFIG_DEBUG_INFO=y
CONFIG_DEBUG_INFO_DWARF4=y
CONFIG_FRAME_POINTER=y
CONFIG_KALLSYMS=y
CONFIG_KALLSYMS_ALL=y

# Disable optimizations that hinder debugging
CONFIG_CC_OPTIMIZE_FOR_SIZE=n
# Consider: CFLAGS += -O0 -g (for specific files)

# Enable all debug features
make menuconfig
# -> Kernel hacking -> Enable plenty of debug options
```

## Quick Reference

| Problem | Tool/Technique |
|---------|---------------|
| Null pointer | KASAN, Oops analysis |
| Use-after-free | KASAN, SLUB debug |
| Memory leak | Kmemleak |
| Deadlock | Lockdep |
| Race condition | KCSAN, stress testing |
| Performance | perf, ftrace |
| Function flow | ftrace, BPF |
| Driver I/O | Dynamic debug, printk |
| Crash analysis | decode_stacktrace.sh |

## x86_64 Assembly for Kernel Debugging

### Register Conventions
```asm
# Function arguments (System V AMD64 ABI)
# rdi, rsi, rdx, rcx, r8, r9      - First 6 integer arguments
# xmm0-xmm7                        - First 8 floating point arguments
# rax                              - Return value
# rbx, rbp, r12-r15               - Callee-saved (preserved across calls)
# rsp                              - Stack pointer
# rip                              - Instruction pointer

# System call convention (different!)
# rax = syscall number
# rdi, rsi, rdx, r10, r8, r9 = args (note: r10 instead of rcx)
```

### Common Instructions
```asm
# Data movement
mov    rax, rbx           # Copy rbx to rax
movzx  eax, byte [rbx]    # Zero-extend byte load
lea    rax, [rbx + rcx*8] # Load effective address (address math)

# Stack operations
push   rax                # Push to stack
pop    rbx                # Pop from stack
call   function           # Push return addr, jump to function
ret                       # Pop return addr, jump there

# Arithmetic
add    rax, 8             # rax += 8
sub    rsp, 0x100         # Allocate 256 bytes on stack
imul   rax, rbx           # rax *= rbx

# Comparisons and jumps
cmp    rax, rbx           # Compare (sets flags)
test   rax, rax           # AND with self (check if zero)
je/jz  label              # Jump if equal/zero
jne/jnz label             # Jump if not equal/not zero
```

### Reading Kernel Disassembly
```bash
# Disassemble with objdump
objdump -d vmlinux | less
objdump -d -S vmlinux    # Interleaved with source

# GDB disassembly
(gdb) disassemble my_function
(gdb) x/20i my_function         # 20 instructions
(gdb) disassemble /m function   # Mixed with source
```

### Decoding Oops Assembly
```
RIP: 0010:my_function+0x42/0x100 [my_module]
Code: 48 89 e5 41 57 41 56 41 55 41 54 53 48 83 ec 28 ...
```
```bash
# Decode the "Code:" line
echo "48 89 e5 41 57 41 56..." | xxd -r -p > /tmp/code.bin
objdump -D -b binary -m i386:x86-64 /tmp/code.bin
```

## AArch64 (ARM64) Assembly for Kernel Debugging

### Register Conventions
```asm
# Function arguments (AAPCS64)
# x0-x7                            - First 8 arguments and return values
# x8                               - Indirect result location
# x9-x15                           - Caller-saved temporaries
# x16-x17                          - Intra-procedure-call scratch (PLT)
# x18                              - Platform register (TLS in Linux)
# x19-x28                          - Callee-saved
# x29 (fp)                         - Frame pointer
# x30 (lr)                         - Link register (return address)
# sp                               - Stack pointer (16-byte aligned)
# pc                               - Program counter

# System registers
# TTBR0_EL1, TTBR1_EL1            - Page table base registers
# SCTLR_EL1                        - System control register
# ESR_EL1                          - Exception syndrome register
# FAR_EL1                          - Fault address register
# ELR_EL1                          - Exception link register
```

### Common AArch64 Instructions
```asm
# Data movement
mov    x0, x1              # Copy x1 to x0
ldr    x0, [x1]            # Load from address
str    x0, [x1]            # Store to address
ldp    x0, x1, [sp]        # Load pair
stp    x0, x1, [sp, #-16]! # Store pair with pre-decrement

# Arithmetic
add    x0, x1, x2          # x0 = x1 + x2
sub    x0, x1, #0x10       # x0 = x1 - 16
madd   x0, x1, x2, x3      # x0 = x1*x2 + x3

# Branching
bl     function            # Branch with link (call)
ret                        # Return (branch to lr)
b.eq   label               # Branch if equal
cbz    x0, label           # Compare and branch if zero

# Memory barriers (critical in kernel)
dmb    sy                  # Data memory barrier
dsb    sy                  # Data synchronization barrier
isb                        # Instruction synchronization barrier
```

### Decoding AArch64 Oops
```bash
# Decode ARM64 oops Code line
echo "d503233f a9bf7bfd..." | xxd -r -p > /tmp/code.bin
aarch64-linux-gnu-objdump -D -b binary -m aarch64 /tmp/code.bin

# Disassemble kernel
aarch64-linux-gnu-objdump -d vmlinux | less
```

## ARM32 Assembly for Kernel Debugging

### Register Conventions
```asm
# Function arguments (AAPCS)
# r0-r3                            - First 4 arguments, r0-r1 for return
# r4-r11                           - Callee-saved
# r12 (ip)                         - Intra-procedure scratch
# r13 (sp)                         - Stack pointer
# r14 (lr)                         - Link register
# r15 (pc)                         - Program counter
# cpsr                             - Current program status register
```

### Common ARM32 Instructions
```asm
# Data movement
mov    r0, r1              # Copy r1 to r0
ldr    r0, [r1]            # Load from address
str    r0, [r1]            # Store to address
ldm    sp!, {r4-r11, pc}   # Load multiple, return

# Push/pop (stack)
push   {r4-r11, lr}        # Save callee-saved and return addr
pop    {r4-r11, pc}        # Restore and return

# Conditional execution
moveq  r0, #1              # Move if equal
addne  r0, r0, #1          # Add if not equal

# Branching
bl     function            # Branch with link
bx     lr                  # Return
beq    label               # Branch if equal
```

### Decoding ARM32 Oops
```bash
# Decode ARM32 code
arm-linux-gnueabi-objdump -D -b binary -m arm /tmp/code.bin

# Thumb mode
arm-linux-gnueabi-objdump -D -b binary -m arm -M force-thumb /tmp/code.bin
```



### Basic GDB Script Syntax
```gdb
# Save as: kernel_debug.gdb
# Run with: gdb -x kernel_debug.gdb vmlinux

# Define custom command
define show_task
    set $task = (struct task_struct *)$arg0
    printf "PID: %d, Comm: %s, State: %ld\n", \
           $task->pid, $task->comm, $task->__state
end

# Loop through task list
define list_tasks
    set $init = &init_task
    set $task = $init
    while 1
        show_task $task
        set $task = (struct task_struct *)((char *)$task->tasks.next - \
                    (size_t)&((struct task_struct *)0)->tasks)
        if $task == $init
            loop_break
        end
    end
end

# Breakpoint with commands
break schedule
commands
    silent
    printf "Switching from PID %d\n", ((struct task_struct *)$rdi)->pid
    continue
end
```

### Kernel Structure Walking
```gdb
# Walk linked list (list_head)
define list_for_each
    set $head = (struct list_head *)$arg0
    set $pos = $head->next
    while $pos != $head
        set $entry = (char *)$pos - $arg1
        printf "Entry at %p\n", $entry
        set $pos = ((struct list_head *)$pos)->next
    end
end

# Decode kernel symbols
define ksym
    set $addr = $arg0
    info symbol $addr
end
```

### Memory Analysis Scripts
```gdb
# Check for stack corruption
define check_stack
    set $t = (struct task_struct *)$arg0
    set $stack = $t->stack
    set $magic = *(unsigned long *)$stack
    if $magic != 0x57AC6E9D
        printf "STACK CORRUPTED! Magic: %lx\n", $magic
    else
        printf "Stack OK\n"
    end
end

# Page flags decoder
define decode_page_flags
    set $flags = $arg0
    printf "Flags: "
    if $flags & (1 << 0)
        printf "locked "
    end
    if $flags & (1 << 4)
        printf "dirty "
    end
    printf "\n"
end
```

### Python Scripting in GDB
```gdb
python
import gdb

class TaskWalker(gdb.Command):
    def __init__(self):
        super().__init__("walk_tasks", gdb.COMMAND_USER)
    
    def invoke(self, arg, from_tty):
        init_task = gdb.lookup_global_symbol("init_task").value()
        task = init_task
        while True:
            pid = int(task["pid"])
            comm = task["comm"].string()
            print(f"PID: {pid}, Name: {comm}")
            tasks = task["tasks"]
            next_ptr = tasks["next"]
            if next_ptr == init_task["tasks"].address:
                break
            offset = gdb.parse_and_eval(
                "(size_t)&((struct task_struct *)0)->tasks"
            )
            task = (next_ptr.cast(gdb.lookup_type("char").pointer()) - 
                    int(offset)).cast(
                gdb.lookup_type("struct task_struct").pointer()
            ).dereference()

TaskWalker()
end
```

## Debugging Workflow


1. **Reproduce consistently** - Create minimal test case
2. **Enable debug options** - KASAN, Lockdep, dynamic debug
3. **Gather information** - dmesg, /proc, /sys, ftrace
4. **Isolate the issue** - Binary search with printk/ftrace
5. **Form hypothesis** - Based on evidence
6. **Test minimally** - Single change at a time
7. **Verify fix** - Run stress tests, check for side effects
