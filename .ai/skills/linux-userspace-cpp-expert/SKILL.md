---
name: linux-userspace-cpp-expert
description: Expert-level Linux userspace application development and debugging in C/C++. Architect-level skills for resolving all types of bugs and implementing complex features. Use for memory issues, crashes, performance problems, concurrency bugs, and system-level programming.
---

# Linux Userspace C/C++ Expert

Architect-level debugging and development expertise for Linux userspace applications in C and C++.

## When to Use This Skill
- Debugging crashes, segfaults, and memory corruption
- Resolving memory leaks and resource management issues
- Debugging race conditions and deadlocks
- Performance optimization and profiling
- System programming (IPC, signals, sockets, file I/O)
- Designing and implementing complex architectures
- Low-level debugging with GDB/LLDB

## Debugging Tools

### GDB - The GNU Debugger
```bash
# Basic usage
gdb ./program
gdb -p <pid>                    # Attach to running process
gdb --args ./program arg1 arg2  # With arguments

# Core dump analysis
ulimit -c unlimited
gdb ./program core

# Remote debugging
gdbserver :1234 ./program
gdb -ex "target remote :1234" ./program
```

**Essential GDB Commands:**
```gdb
# Execution control
run / r                    # Start program
continue / c               # Continue execution
next / n                   # Step over
step / s                   # Step into
finish                     # Run until function returns
until <line>               # Run until line

# Breakpoints
break main                 # Break at function
break file.cpp:123         # Break at line
break *0x400abc            # Break at address
watch var                  # Break on variable change
catch throw                # Break on C++ exception
condition 1 x > 10         # Conditional breakpoint
info breakpoints           # List breakpoints
delete 1                   # Delete breakpoint

# Inspection
print var                  # Print variable
print *ptr                 # Dereference pointer
print arr[0]@10            # Print 10 array elements
print/x var                # Print in hex
print ((Type*)ptr)->field  # Cast and access
display var                # Auto-print on each step

# Memory
x/10x $rsp                 # Examine 10 hex words at stack
x/s str                    # Examine as string
x/i $pc                    # Examine as instruction
info registers             # Show registers

# Stack
backtrace / bt             # Full backtrace
bt full                    # Backtrace with locals
frame 3                    # Select frame
up / down                  # Navigate frames
info locals                # Local variables
info args                  # Function arguments

# Threads
info threads               # List threads
thread 2                   # Switch to thread
thread apply all bt        # Backtrace all threads

# Advanced
set var = value            # Modify variable
call function(args)        # Call function
ptype variable             # Show type
whatis expression          # Show expression type
```

### Valgrind - Memory Analysis
```bash
# Memory leak detection
valgrind --leak-check=full --show-leak-kinds=all ./program

# Track origins of uninitialized values
valgrind --track-origins=yes ./program

# Memory error detection
valgrind --tool=memcheck ./program

# Cache profiling
valgrind --tool=cachegrind ./program
cg_annotate cachegrind.out.*

# Call graph profiling
valgrind --tool=callgrind ./program
kcachegrind callgrind.out.*

# Thread error detection
valgrind --tool=helgrind ./program   # Race detection
valgrind --tool=drd ./program        # Alternative race detector
```

### AddressSanitizer (ASan)
```bash
# Compile with ASan
g++ -fsanitize=address -fno-omit-frame-pointer -g program.cpp

# Detects:
# - Use after free
# - Heap/stack/global buffer overflow
# - Use after return
# - Double free
# - Memory leaks (with -fsanitize=address,leak)

# Environment options
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./program
```

### ThreadSanitizer (TSan)
```bash
# Compile with TSan
g++ -fsanitize=thread -g program.cpp

# Detects:
# - Data races
# - Lock order inversions
# - Deadlocks
```

### UndefinedBehaviorSanitizer (UBSan)
```bash
# Compile with UBSan
g++ -fsanitize=undefined -g program.cpp

# Detects:
# - Signed integer overflow
# - Null pointer dereference
# - Array index out of bounds
# - Misaligned accesses
# - Invalid casts
```

### Memory Sanitizer (MSan)
```bash
# Compile with MSan (Clang only)
clang++ -fsanitize=memory -fno-omit-frame-pointer -g program.cpp

# Detects uninitialized memory reads
```

## Memory & Stack Analysis

### Process Memory Layout
```bash
# View memory maps
cat /proc/<pid>/maps
pmap <pid>
pmap -x <pid>  # Extended info with RSS

# Memory usage summary
cat /proc/<pid>/status | grep -E 'Vm|Rss|Stack'
cat /proc/<pid>/statm

# Memory layout regions (typical x86_64)
# 0x400000           - Text segment (code)
# 0x600000           - Data segment
# Heap grows up      - Dynamic allocation
# ...                - Shared libraries
# Stack grows down   - Local variables
# 0x7fffffffffff     - Top of user space
```

### Stack Analysis with GDB
```gdb
# View stack frame layout
(gdb) info frame
(gdb) info frame 0   # Detailed frame info

# Examine stack memory
(gdb) x/32xg $rsp    # 32 quad-words from stack pointer
(gdb) x/32xg $rbp    # From base pointer

# Stack pointer and base pointer
(gdb) print $rsp
(gdb) print $rbp
(gdb) print $rbp - $rsp  # Current frame size

# View all frames' locals
(gdb) bt full

# Check for stack overflow (stack guard)
(gdb) x/8xg $rsp - 0x1000  # Check below stack

# Unwind stack manually
(gdb) set $fp = $rbp
(gdb) while $fp != 0
 > x/2xg $fp    # Show saved rbp and return addr
 > set $fp = *(void**)$fp
 > end
```

### Heap Analysis
```bash
# glibc malloc debugging
export MALLOC_CHECK_=3       # Abort on corruption
export MALLOC_PERTURB_=0xAA  # Fill freed memory with pattern

# mtrace - memory trace
export MALLOC_TRACE=mtrace.log
mtrace ./program mtrace.log

# Heap info at runtime (glibc)
gdb -p <pid>
(gdb) call malloc_info(0, stdout)
(gdb) call malloc_stats()
```

```gdb
# GDB heap commands (with glibc)
(gdb) heap            # Overview (requires gef/pwndbg)
(gdb) heap bins       # Show free lists
(gdb) heap chunks     # List all chunks

# Manual heap inspection
(gdb) print *(struct malloc_chunk*)($ptr - 16)

# Heap boundaries from aux vector
(gdb) info auxv

# Find heap start
(gdb) info proc mappings
```

### Stack Overflow Detection
```cpp
// Compile-time protection
// -fstack-protector       : Protect functions with large arrays
// -fstack-protector-all   : Protect all functions
// -fstack-protector-strong: Better heuristic (recommended)
// -fstack-clash-protection: Detect stack clash attacks

// Runtime stack limit
#include <sys/resource.h>
struct rlimit rl;
getrlimit(RLIMIT_STACK, &rl);
printf("Stack limit: soft=%lu, hard=%lu\n", rl.rlim_cur, rl.rlim_max);

// Check remaining stack space
#include <pthread.h>
void check_stack_remaining() {
    pthread_attr_t attr;
    void* stack_addr;
    size_t stack_size;
    
    pthread_getattr_np(pthread_self(), &attr);
    pthread_attr_getstack(&attr, &stack_addr, &stack_size);
    
    char dummy;
    size_t used = (char*)stack_addr + stack_size - &dummy;
    size_t remaining = stack_size - used;
    printf("Stack: used=%zu, remaining=%zu\n", used, remaining);
    
    pthread_attr_destroy(&attr);
}
```

### Core Dump Analysis
```bash
# Enable core dumps
ulimit -c unlimited
echo "/tmp/core.%e.%p" > /proc/sys/kernel/core_pattern

# Analyze core with GDB
gdb ./program /tmp/core.program.12345
(gdb) bt                 # Backtrace at crash
(gdb) bt full            # With local variables
(gdb) info registers     # Register state at crash
(gdb) x/10i $rip         # Instructions at crash point

# Check signal that caused core
(gdb) print $_siginfo
(gdb) print $_siginfo._sifields._sigfault.si_addr  # Fault address
```

### Memory Mapping Techniques
```cpp
#include <sys/mman.h>

// Guard pages for buffer overflow detection
void* guarded_alloc(size_t size) {
    size_t page_size = sysconf(_SC_PAGESIZE);
    size_t total = ((size + page_size - 1) / page_size + 2) * page_size;
    
    void* base = mmap(NULL, total, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    
    // Guard page at start
    mprotect(base, page_size, PROT_NONE);
    // Guard page at end
    mprotect((char*)base + total - page_size, page_size, PROT_NONE);
    
    return (char*)base + page_size;
}

// Check if pointer is in valid mapped region
bool is_mapped(void* ptr) {
    unsigned char vec[1];
    return mincore(ptr, 1, vec) == 0;
}
```


## Performance Profiling

### perf
```bash
# CPU profiling
perf record -g ./program
perf report

# Flame graphs
perf record -F 99 -g ./program
perf script | stackcollapse-perf.pl | flamegraph.pl > perf.svg

# Specific events
perf stat -e cache-misses,cache-references,cycles,instructions ./program
perf record -e cache-misses -g ./program

# System-wide
perf top
perf record -a -g sleep 10
```

### gprof
```bash
# Compile with profiling
g++ -pg -g program.cpp -o program
./program
gprof program gmon.out > analysis.txt
```

### strace / ltrace
```bash
# System call tracing
strace ./program
strace -f ./program              # Follow forks
strace -e open,read,write ./program  # Filter syscalls
strace -c ./program              # Summary
strace -p <pid>                  # Attach to process

# Library call tracing
ltrace ./program
ltrace -e malloc+free ./program
```

## Memory Management Patterns

### RAII - Resource Acquisition Is Initialization
```cpp
// Smart pointers
std::unique_ptr<Resource> ptr = std::make_unique<Resource>();
std::shared_ptr<Resource> shared = std::make_shared<Resource>();
std::weak_ptr<Resource> weak = shared;

// Lock guards
std::lock_guard<std::mutex> lock(mutex);
std::unique_lock<std::mutex> ulock(mutex);
std::scoped_lock lock(mutex1, mutex2);  // C++17

// File handles
class File {
    int fd_;
public:
    File(const char* path) : fd_(open(path, O_RDONLY)) {
        if (fd_ < 0) throw std::system_error(errno, std::system_category());
    }
    ~File() { if (fd_ >= 0) close(fd_); }
    File(const File&) = delete;
    File& operator=(const File&) = delete;
    File(File&& other) noexcept : fd_(std::exchange(other.fd_, -1)) {}
};
```

### Common Memory Bugs
```cpp
// 1. Use after free
ptr = malloc(size);
free(ptr);
*ptr = value;  // BUG!

// 2. Double free
free(ptr);
free(ptr);  // BUG!

// 3. Buffer overflow
char buf[10];
strcpy(buf, "this string is too long");  // BUG!

// 4. Memory leak
ptr = malloc(size);
ptr = malloc(size);  // Previous allocation leaked!

// 5. Uninitialized memory
int x;
if (x > 10) { }  // BUG! x is uninitialized

// 6. Off-by-one
for (int i = 0; i <= arr_size; i++)  // BUG! Should be <
    arr[i] = 0;
```

## Concurrency Patterns

### Thread-Safe Patterns
```cpp
// 1. Mutex protection
class ThreadSafe {
    mutable std::mutex mutex_;
    int data_;
public:
    int get() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return data_;
    }
    void set(int value) {
        std::lock_guard<std::mutex> lock(mutex_);
        data_ = value;
    }
};

// 2. Read-write lock
std::shared_mutex rw_mutex;
// Reader
{
    std::shared_lock lock(rw_mutex);
    // read data
}
// Writer
{
    std::unique_lock lock(rw_mutex);
    // modify data
}

// 3. Lock-free atomics
std::atomic<int> counter{0};
counter.fetch_add(1, std::memory_order_relaxed);

// 4. Condition variables
std::condition_variable cv;
std::mutex cv_mutex;
bool ready = false;

// Producer
{
    std::lock_guard lock(cv_mutex);
    ready = true;
}
cv.notify_one();

// Consumer
{
    std::unique_lock lock(cv_mutex);
    cv.wait(lock, []{ return ready; });
}
```

### Deadlock Prevention
```cpp
// 1. Lock ordering - always acquire in same order
void transfer(Account& a, Account& b) {
    Account* first = &a < &b ? &a : &b;
    Account* second = &a < &b ? &b : &a;
    std::lock_guard lock1(first->mutex);
    std::lock_guard lock2(second->mutex);
}

// 2. std::scoped_lock - deadlock-free multi-lock
std::scoped_lock lock(mutex1, mutex2, mutex3);

// 3. Try-lock with backoff
while (true) {
    std::unique_lock lock1(mutex1, std::defer_lock);
    std::unique_lock lock2(mutex2, std::defer_lock);
    if (std::try_lock(lock1, lock2) == -1) break;
    std::this_thread::yield();
}
```

## System Programming

### Signal Handling
```cpp
#include <signal.h>
#include <atomic>

std::atomic<bool> shutdown_requested{false};

void signal_handler(int sig) {
    shutdown_requested.store(true);
}

int main() {
    struct sigaction sa = {};
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, nullptr);
    sigaction(SIGTERM, &sa, nullptr);
    
    while (!shutdown_requested.load()) {
        // main loop
    }
}
```

### IPC - Inter-Process Communication
```cpp
// Shared memory
int fd = shm_open("/my_shm", O_CREAT | O_RDWR, 0666);
ftruncate(fd, size);
void* ptr = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);

// Message queues
mqd_t mq = mq_open("/my_queue", O_CREAT | O_RDWR, 0666, &attr);
mq_send(mq, buffer, len, priority);
mq_receive(mq, buffer, len, &priority);

// Unix domain sockets
int fd = socket(AF_UNIX, SOCK_STREAM, 0);
struct sockaddr_un addr = {.sun_family = AF_UNIX};
strcpy(addr.sun_path, "/tmp/socket");
bind(fd, (struct sockaddr*)&addr, sizeof(addr));
```

### epoll - Scalable I/O
```cpp
int epfd = epoll_create1(0);

struct epoll_event ev = {
    .events = EPOLLIN | EPOLLET,  // Edge-triggered
    .data.fd = fd
};
epoll_ctl(epfd, EPOLL_CTL_ADD, fd, &ev);

struct epoll_event events[MAX_EVENTS];
int n = epoll_wait(epfd, events, MAX_EVENTS, timeout_ms);
for (int i = 0; i < n; i++) {
    if (events[i].events & EPOLLIN) {
        handle_read(events[i].data.fd);
    }
}
```

## Architecture Patterns

### Dependency Injection
```cpp
class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string& msg) = 0;
};

class Service {
    std::unique_ptr<ILogger> logger_;
public:
    explicit Service(std::unique_ptr<ILogger> logger)
        : logger_(std::move(logger)) {}
};
```

### Observer Pattern
```cpp
template<typename... Args>
class Signal {
    std::vector<std::function<void(Args...)>> slots_;
public:
    void connect(std::function<void(Args...)> slot) {
        slots_.push_back(std::move(slot));
    }
    void emit(Args... args) {
        for (auto& slot : slots_) slot(args...);
    }
};
```

### Object Pool
```cpp
template<typename T>
class ObjectPool {
    std::vector<std::unique_ptr<T>> pool_;
    std::stack<T*> available_;
    std::mutex mutex_;
public:
    T* acquire() {
        std::lock_guard lock(mutex_);
        if (available_.empty()) {
            pool_.push_back(std::make_unique<T>());
            return pool_.back().get();
        }
        T* obj = available_.top();
        available_.pop();
        return obj;
    }
    void release(T* obj) {
        std::lock_guard lock(mutex_);
        available_.push(obj);
    }
};
```

## Build System & Toolchain

### CMake Best Practices
```cmake
cmake_minimum_required(VERSION 3.16)
project(MyProject VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Debug/Release flags
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -fsanitize=address,undefined")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# Warnings
add_compile_options(-Wall -Wextra -Wpedantic -Werror)

# Targets
add_library(mylib STATIC src/lib.cpp)
add_executable(myapp src/main.cpp)
target_link_libraries(myapp PRIVATE mylib)
```

### Compiler Warnings
```bash
# Enable all warnings
g++ -Wall -Wextra -Wpedantic -Werror \
    -Wshadow -Wnon-virtual-dtor -Wold-style-cast \
    -Wcast-align -Wunused -Woverloaded-virtual \
    -Wconversion -Wsign-conversion -Wnull-dereference \
    -Wdouble-promotion -Wformat=2 \
    program.cpp
```

## x86_64 Assembly for Userspace Debugging

### Register Conventions (System V AMD64 ABI)
```asm
# Function arguments
# rdi, rsi, rdx, rcx, r8, r9      - First 6 integer/pointer args
# xmm0-xmm7                        - First 8 float/double args
# Stack                            - Additional arguments

# Return values
# rax                              - Integer/pointer return
# xmm0                             - Float/double return

# Callee-saved (must preserve)
# rbx, rbp, r12, r13, r14, r15

# Caller-saved (may be clobbered)
# rax, rcx, rdx, rsi, rdi, r8, r9, r10, r11
```

### Common Instructions for Debugging
```asm
# Function prologue
push   rbp                # Save old frame pointer
mov    rbp, rsp           # Set new frame pointer
sub    rsp, 0x40          # Allocate 64 bytes for locals

# Function epilogue
leave                     # mov rsp, rbp; pop rbp
ret                       # Return to caller

# Memory access patterns
mov    rax, [rbx]         # Load from address in rbx
mov    [rbx], rax         # Store to address in rbx
mov    rax, [rbx + rcx*8] # Array indexing
```

### Reading Disassembly
```bash
# Disassemble with objdump
objdump -d -M intel program        # Intel syntax
objdump -d -S program              # Interleave with source

# GDB disassembly
(gdb) set disassembly-flavor intel
(gdb) disas main                   # Disassemble function
(gdb) disas /m main                # Mixed with source
(gdb) x/20i $pc                    # 20 instructions from current
```

### Identifying Common Bugs in Assembly
```asm
# Null pointer dereference
mov    rax, [0x0]              # Accessing address 0

# Stack buffer overflow
sub    rsp, 0x10               # 16-byte buffer
lea    rdi, [rsp]
mov    esi, 0x100              # Writing 256 bytes!
call   read

# Use after free
call   free
mov    [rbx], rax              # Writing to freed memory!
```

## AArch64 (ARM64) Assembly for Userspace Debugging

### Register Conventions (AAPCS64)
```asm
# Function arguments
# x0-x7                            - First 8 arguments
# x0-x1                            - Return values (x0 primary)
# d0-d7                            - First 8 FP arguments

# Callee-saved (must preserve)
# x19-x28                          - General purpose
# x29 (fp)                         - Frame pointer
# x30 (lr)                         - Link register

# Caller-saved (may be clobbered)
# x0-x18

# Special registers
# sp                               - Stack pointer (16-byte aligned)
# pc                               - Program counter
# xzr/wzr                          - Zero register
```

### Common AArch64 Instructions
```asm
# Function prologue
stp    x29, x30, [sp, #-16]!  # Save fp and lr
mov    x29, sp                 # Set frame pointer

# Function epilogue
ldp    x29, x30, [sp], #16     # Restore fp and lr
ret                            # Return

# Memory access
ldr    x0, [x1]                # Load 64-bit
ldr    w0, [x1]                # Load 32-bit
ldrb   w0, [x1]                # Load byte
str    x0, [x1, x2, lsl #3]    # Store with scaled index

# Addressing modes
ldr    x0, [x1, #8]            # Immediate offset
ldr    x0, [x1, #8]!           # Pre-index
ldr    x0, [x1], #8            # Post-index
```

### Reading AArch64 Disassembly
```bash
# Disassemble with objdump
aarch64-linux-gnu-objdump -d program
aarch64-linux-gnu-objdump -d -S program  # With source

# GDB on ARM64
(gdb) disas main
(gdb) x/20i $pc
(gdb) info registers
```

### Common Bugs in AArch64 Assembly
```asm
# Null pointer dereference
ldr    x0, [xzr]               # Load from address 0

# Unaligned access (can cause SIGBUS)
ldr    x0, [x1]                # x1 not 8-byte aligned

# Missing barrier
str    x0, [x1]                # Store to shared memory
# dmb sy                       # Missing barrier!
ldr    x2, [x3]                # May see stale data
```

## ARM32 Assembly for Userspace Debugging

### Register Conventions (AAPCS)
```asm
# Function arguments
# r0-r3                            - First 4 arguments
# r0-r1                            - Return values

# Callee-saved (must preserve)
# r4-r11

# Special registers
# r12 (ip)                         - Scratch
# r13 (sp)                         - Stack pointer
# r14 (lr)                         - Link register
# r15 (pc)                         - Program counter
```

### Common ARM32 Instructions
```asm
# Function prologue
push   {r4-r11, lr}            # Save callee-saved and lr

# Function epilogue
pop    {r4-r11, pc}            # Restore and return

# Memory access
ldr    r0, [r1]                # Load word
ldrb   r0, [r1]                # Load byte
str    r0, [r1, r2, lsl #2]    # Store with scaled index

# Conditional execution (unique to ARM)
cmp    r0, #0
moveq  r0, #1                  # Move if equal
movne  r0, #0                  # Move if not equal
```

### Reading ARM32 Disassembly
```bash
# Disassemble
arm-linux-gnueabihf-objdump -d program
arm-linux-gnueabihf-objdump -d -M force-thumb program  # Thumb mode

# GDB on ARM32
(gdb) disas main
(gdb) info registers
(gdb) display/i $pc
```



### Basic GDB Script Syntax
```gdb
# Save as: debug.gdb
# Run with: gdb -x debug.gdb ./program

# Define custom command
define print_vector
    set $vec = (std::vector<int> *)$arg0
    set $size = $vec->_M_impl._M_finish - $vec->_M_impl._M_start
    set $i = 0
    while $i < $size
        print *($vec->_M_impl._M_start + $i)
        set $i = $i + 1
    end
end

# Breakpoint with automatic commands
break malloc
commands
    silent
    printf "malloc(%lu) from ", (unsigned long)$rdi
    bt 1
    continue
end
```

### Memory Debugging Scripts
```gdb
# Track allocations
define track_alloc
    break malloc
    commands
        silent
        set $alloc_size = $rdi
    end
end

# Detect double free
define detect_double_free
    set $freed_ptrs = (void **)malloc(1000 * sizeof(void*))
    set $freed_count = 0
    break free
    commands
        silent
        set $i = 0
        while $i < $freed_count
            if $freed_ptrs[$i] == $rdi
                printf "DOUBLE FREE: %p\n", $rdi
                bt
            end
            set $i = $i + 1
        end
        set $freed_ptrs[$freed_count] = $rdi
        set $freed_count = $freed_count + 1
        continue
    end
end

# Memory dump helper
define hexdump
    set $addr = $arg0
    set $len = $arg1
    set $i = 0
    while $i < $len
        if ($i % 16) == 0
            printf "\n%p: ", $addr + $i
        end
        printf "%02x ", *(unsigned char *)($addr + $i)
        set $i = $i + 1
    end
    printf "\n"
end
```

### Python-Enhanced GDB Scripts
```gdb
python
import gdb

# Breakpoint command class
class TraceBreakpoint(gdb.Breakpoint):
    def __init__(self, spec):
        super().__init__(spec)
    
    def stop(self):
        frame = gdb.selected_frame()
        print(f"Hit {self.location} in {frame.name()}")
        for sym in frame.block():
            if sym.is_argument:
                val = frame.read_var(sym)
                print(f"  {sym.name} = {val}")
        return False  # Don't stop

# Automatic crash analysis
class CrashHandler:
    def __call__(self, event):
        if hasattr(event, 'stop_signal'):
            if event.stop_signal in ['SIGSEGV', 'SIGABRT']:
                print("=== CRASH DETECTED ===")
                gdb.execute("bt full")
                gdb.execute("info registers")

gdb.events.stop.connect(CrashHandler())
end
```

### Automation and Logging
```gdb
# .gdbinit for project
set print pretty on
set print object on
set pagination off
set confirm off
set history save on
set history size 10000
set logging file trace.log
set logging on
```

## Debugging Workflow


1. **Reproduce** - Create minimal test case
2. **Isolate** - Binary search to narrow cause
3. **Instrument** - Add logging, sanitizers, tracing
4. **Analyze** - Use appropriate tools (GDB, Valgrind, perf)
5. **Hypothesize** - Form theory based on evidence
6. **Fix** - Make minimal change
7. **Verify** - Test fix, check for side effects
8. **Prevent** - Add tests, static analysis

## Quick Reference

| Bug Type | Tools |
|----------|-------|
| Crash/Segfault | GDB, ASan, core dump |
| Memory leak | Valgrind, ASan+leak |
| Buffer overflow | ASan, Valgrind |
| Use after free | ASan, Valgrind |
| Race condition | TSan, Helgrind |
| Deadlock | TSan, GDB thread info |
| Uninitialized | MSan, Valgrind |
| Undefined behavior | UBSan |
| Performance | perf, gprof, Callgrind |
| System calls | strace |
| Library calls | ltrace |
