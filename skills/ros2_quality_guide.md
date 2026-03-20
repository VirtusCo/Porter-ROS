# ROS 2 Quality Guide — Skill File

> Source: https://docs.ros.org/en/jazzy/The-ROS2-Project/Contributing/Quality-Guide.html
> Distro: Jazzy Jalisco

---

## Purpose

Guidance on improving software quality for ROS 2 packages.
Focuses on "Reliability", "Security", "Maintainability", "Determinism".
Applies to core, application, and ecosystem packages (C++ and Python).

---

## 1. Static Code Analysis with ament

### Context
- You have C++ production code in an ament-based ROS 2 package.
- You want static analysis to run automatically during build.

### Solution

Add to `CMakeLists.txt`:

```cmake
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()
```

Add to `package.xml`:

```xml
<test_depend>ament_lint_auto</test_depend>
<test_depend>ament_lint_common</test_depend>
```

### Result
- All `ament`-supported static analysis tools run as part of package build.
- Tools NOT supported by ament must be run separately.

### Examples
- `rclcpp/rclcpp/CMakeLists.txt` — https://github.com/ros2/rclcpp/blob/jazzy/rclcpp/CMakeLists.txt
- `rclcpp_lifecycle/CMakeLists.txt` — https://github.com/ros2/rclcpp/blob/jazzy/rclcpp_lifecycle/CMakeLists.txt

---

## 2. Static Thread Safety Analysis via Code Annotation

### Context
- Developing/debugging multithreaded C++ code.
- Accessing data from multiple threads.

### Problem
- Data races and deadlocks can cause critical bugs.

### Solution
- Use **Clang's Thread Safety Analysis** with code annotations.
- ROS 2 provides macros in `rcpputils/thread_safety_annotations.hpp`.

### Key Macros

| Macro | Purpose |
|---|---|
| `RCPPUTILS_TSA_GUARDED_BY(mutex)` | Marks data as protected by a mutex |
| `RCPPUTILS_TSA_REQUIRES(mutex)` | Function requires mutex to be held |
| `RCPPUTILS_TSA_REQUIRES(!mutex)` | Negative capability — mutex must NOT be held |

### Implementation Steps

#### Step 1 — Enable Analysis (CMake)

```cmake
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wthread-safety)   # whole package
  # OR
  target_compile_options(${MY_TARGET} PUBLIC -Wthread-safety)  # single target
endif()
```

#### Step 2 — Annotate Data Members

```cpp
class Foo {
public:
  void incr(int amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    bar += amount;
  }

  void get() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return bar;
  }

private:
  mutable std::mutex mutex_;
  int bar RCPPUTILS_TSA_GUARDED_BY(mutex_) = 0;
};
```

#### Step 3 — Fix Warnings
- The compiler will warn if guarded data is accessed without holding the lock.
- Lock before accessing any `GUARDED_BY` members.

#### Step 4 — Refactor to Private-Mutex Pattern
- Keep `mutex` as `private:` member.
- Provide specialized interfaces instead of exposing underlying structures.
- Consider copying small data to avoid blocking.

#### Step 5 — Enable Negative Capability Analysis (Optional)
- Add `-Wthread-safety-negative` flag.
- On any function that acquires a lock: `RCPPUTILS_TSA_REQUIRES(!mutex)`.

### How to Run

**CI**: Nightly job with `libcxx` surfaces issues as "Unstable".

**Local options** (all equivalent):

```bash
# Option A: colcon mixin
colcon build --mixin clang-libcxx

# Option B: CMake args
colcon build --cmake-args \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_CXX_FLAGS='-stdlib=libc++ -D_LIBCPP_ENABLE_THREAD_SAFETY_ANNOTATIONS' \
  -DFORCE_BUILD_VENDOR_PKG=ON --no-warn-unused-cli

# Option C: Environment override
CC=clang CXX=clang++ colcon build --cmake-args \
  -DCMAKE_CXX_FLAGS='-stdlib=libc++ -D_LIBCPP_ENABLE_THREAD_SAFETY_ANNOTATIONS' \
  -DFORCE_BUILD_VENDOR_PKG=ON --no-warn-unused-cli
```

### Important Notes on std:: Threading
- `libc++` (LLVM) annotates `std::mutex` and `std::lock_guard` for Thread Safety Analysis.
- `libstdc++` (GNU, default on Linux) does NOT annotate them.
- **Must use `libc++`** to get Thread Safety Analysis with `std::` types.

---

## 3. Dynamic Analysis (Data Races & Deadlocks)

### Context
- Developing/debugging multithreaded C++ code.
- Using pthreads or C++11 threading + llvm libc++.
- No static linking of Libc/libstdc++.
- No non-position-independent executables.

### Problem
- Data races and deadlocks cannot be found by static analysis alone.
- They may not appear during normal debugging/testing.

### Solution
- Use **Clang ThreadSanitizer** (`-fsanitize=thread`).

### Implementation

```bash
# Compile and link with ThreadSanitizer instrumentation
clang++ -fsanitize=thread -o my_binary my_source.cpp
```

### Selective Instrumentation
- **Conditional compilation**: Use `__has_feature(thread_sanitizer)`.
- **Exclude functions**: `__attribute__((no_sanitize("thread")))`.
- **Exclude files**: Use `--fsanitize-blacklist` with a Sanitizer Special Case List.

### Resulting Context
- Higher chance of finding data races and deadlocks before deployment.
- Analysis is in beta — results may lack 100% reliability.
- Overhead: instrumented code needs more memory per thread and maps large virtual address space.
- Maintenance overhead: may need separate instrumented/non-instrumented branches.

---

## Quick Reference: Quality Checklist

- [ ] `ament_lint_auto` + `ament_lint_common` in CMakeLists.txt and package.xml
- [ ] Thread safety annotations on all shared mutable data
- [ ] `-Wthread-safety` enabled for Clang builds
- [ ] ThreadSanitizer runs on multithreaded code
- [ ] Code coverage ≥ 95% line coverage
- [ ] All linters from `ament_lint_common` passing
- [ ] Compiler flags: `-Wall -Wextra -Wpedantic`
- [ ] `cppcheck` via `ament_cppcheck`
