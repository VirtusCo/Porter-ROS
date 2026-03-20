# Zephyr RTOS — Kernel Services — Skill File

> Source: https://docs.zephyrproject.org/latest/kernel/services/index.html
> RTOS: Zephyr · Target: ESP32-DevKitC

---

## Overview

The Zephyr kernel provides fundamental OS services for real-time, resource-constrained systems. All kernel objects are statically defined at compile time (no dynamic allocation by default).

---

## 1. Threads

### Thread Properties
- Each thread has: stack area, thread control block, entry point function, scheduling priority, start delay
- Threads can be **preemptible** (priority ≥ 0) or **cooperative** (priority < 0)
- Thread states: running, ready, suspended, waiting, terminated

### Thread Creation

```c
#define STACK_SIZE 1024
#define PRIORITY 5

K_THREAD_STACK_DEFINE(my_stack, STACK_SIZE);
struct k_thread my_thread_data;

void my_entry(void *p1, void *p2, void *p3) {
    while (1) {
        /* thread work */
        k_msleep(100);
    }
}

/* Create thread */
k_tid_t tid = k_thread_create(&my_thread_data, my_stack,
    K_THREAD_STACK_SIZEOF(my_stack),
    my_entry, NULL, NULL, NULL,
    PRIORITY, 0, K_NO_WAIT);

/* Or use static macro */
K_THREAD_DEFINE(my_tid, STACK_SIZE, my_entry, NULL, NULL, NULL,
    PRIORITY, 0, 0);
```

### Thread Naming
```c
k_thread_name_set(tid, "motor_ctrl");
```

---

## 2. Scheduling

- **Priority-based preemptive** scheduling (default)
- Cooperative threads (negative priority) run until they yield
- Preemptible threads can be preempted by higher-priority threads
- Same-priority threads: time-slicing (if `CONFIG_TIMESLICING=y`)
- **CPU Idling**: kernel enters idle when no threads are runnable (`k_cpu_idle()`)

### System Threads
- **Main thread**: runs `main()`, default priority 0
- **Idle thread**: lowest priority, runs when nothing else to do
- **System workqueue**: kernel work queue for deferred processing

---

## 3. Interrupts

- ISRs have **higher priority than all threads**
- ISRs should be short — defer heavy work to threads/workqueues
- **Cannot call blocking kernel APIs from ISR context**
- Use `k_is_in_isr()` to check context

### ISR Rules
- No sleeping/blocking in ISR
- Use `K_NO_WAIT` for timeouts in ISR context
- Signal threads via semaphores, events, or work items from ISR

---

## 4. Synchronization Primitives

### Semaphores
```c
K_SEM_DEFINE(my_sem, 0, 1);  /* initial=0, limit=1 */

/* Give (signal) — safe from ISR */
k_sem_give(&my_sem);

/* Take (wait) */
k_sem_take(&my_sem, K_FOREVER);
k_sem_take(&my_sem, K_MSEC(100));  /* with timeout */
```

### Mutexes
```c
K_MUTEX_DEFINE(my_mutex);

k_mutex_lock(&my_mutex, K_FOREVER);
/* critical section */
k_mutex_unlock(&my_mutex);
```
- Supports **priority inheritance** to avoid priority inversion
- **Not usable from ISR context**

### Condition Variables
```c
K_CONDVAR_DEFINE(my_condvar);

/* Wait (must hold mutex) */
k_condvar_wait(&my_condvar, &my_mutex, K_FOREVER);

/* Signal one waiter */
k_condvar_signal(&my_condvar);

/* Signal all waiters */
k_condvar_broadcast(&my_condvar);
```

### Events (Bitmask)
```c
K_EVENT_DEFINE(my_events);

/* Post events from any context */
k_event_post(&my_events, BIT(0) | BIT(1));

/* Wait for any/all events */
uint32_t events = k_event_wait(&my_events, BIT(0) | BIT(1),
    true,  /* reset events on match */
    K_FOREVER);
```

### Polling
- Wait on multiple kernel objects simultaneously
- Supports: semaphores, FIFOs, message queues, signals
```c
struct k_poll_event events[2] = {
    K_POLL_EVENT_INITIALIZER(K_POLL_TYPE_SEM_AVAILABLE, K_POLL_MODE_NOTIFY_ONLY, &sem1),
    K_POLL_EVENT_INITIALIZER(K_POLL_TYPE_FIFO_DATA_AVAILABLE, K_POLL_MODE_NOTIFY_ONLY, &fifo1),
};
k_poll(events, 2, K_FOREVER);
```

---

## 5. Data Passing Mechanisms

| Mechanism | Copy? | ISR Send | ISR Recv | Overrun? | Best For |
|-----------|-------|----------|----------|----------|----------|
| **FIFO** | No (pointer) | ✓ | ✓ | N/A | Linked-list queue |
| **LIFO** | No (pointer) | ✓ | ✓ | N/A | Stack-like queue |
| **Stack** | Yes (word) | ✓ | ✓ | N/A | Simple word passing |
| **Message Queue** | Yes (copy) | ✓ | ✓ | Drop/Overwrite | Fixed-size messages |
| **Mailbox** | Yes (optional) | ✗ | ✗ | N/A | Thread-to-thread |
| **Pipe** | Yes (stream) | ✗ | ✗ | N/A | Byte streams |

### Message Queue (Most Common)
```c
K_MSGQ_DEFINE(my_msgq, sizeof(struct sensor_data), 10, 4);

/* Send */
struct sensor_data data = { .x = 1, .y = 2 };
k_msgq_put(&my_msgq, &data, K_MSEC(100));

/* Receive */
struct sensor_data rx;
k_msgq_get(&my_msgq, &rx, K_FOREVER);
```

---

## 6. Timers & Timing

### Kernel Timer
```c
void my_timer_handler(struct k_timer *timer) {
    /* Called in ISR context! Keep short. */
}

K_TIMER_DEFINE(my_timer, my_timer_handler, NULL);

k_timer_start(&my_timer, K_MSEC(100), K_MSEC(100));  /* delay, period */
k_timer_stop(&my_timer);
```

### Timing Functions
```c
k_msleep(100);           /* Sleep 100ms */
k_usleep(500);           /* Sleep 500µs */
k_busy_wait(10);         /* Busy-wait 10µs (no context switch) */

int64_t uptime = k_uptime_get();        /* ms since boot */
uint32_t cycles = k_cycle_get_32();     /* CPU cycles */
```

---

## 7. Workqueue (Deferred Work)

```c
/* Use system workqueue */
struct k_work my_work;

void work_handler(struct k_work *work) {
    /* Runs in system workqueue thread context */
}

k_work_init(&my_work, work_handler);
k_work_submit(&my_work);

/* Delayed work */
struct k_work_delayable my_delayed_work;
k_work_init_delayable(&my_delayed_work, work_handler);
k_work_schedule(&my_delayed_work, K_MSEC(500));
```

---

## 8. Memory Management

- **Memory Slabs**: Fixed-size block allocation (deterministic, no fragmentation)
- **Memory Heaps**: Variable-size allocation (may fragment)
- Use slabs for real-time predictability

```c
K_MEM_SLAB_DEFINE(my_slab, 64, 10, 4);  /* block_size, num_blocks, align */

void *block;
k_mem_slab_alloc(&my_slab, &block, K_NO_WAIT);
/* use block */
k_mem_slab_free(&my_slab, block);
```

---

## 9. Atomic Operations

```c
#include <zephyr/sys/atomic.h>

atomic_t my_val = ATOMIC_INIT(0);
atomic_inc(&my_val);
atomic_dec(&my_val);
atomic_set(&my_val, 42);
atomic_val_t old = atomic_get(&my_val);
```

---

## 10. Fatal Error Handling

- Fatal errors: stack overflow, kernel panic, unhandled exceptions
- Default handler: logs error and resets system
- Custom handler via `k_sys_fatal_error_handler()`
- Enable `CONFIG_THREAD_STACK_INFO=y` for stack overflow detection
