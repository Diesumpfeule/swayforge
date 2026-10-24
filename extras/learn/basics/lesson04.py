# LESSON 4 – Lists and loops
# Run it:   python3 lesson04.py

fruits = ["apple", "banana", "cherry"]      # a LIST: many values in one variable
print(fruits[0])                            # apple   (counting starts at 0!)
print(fruits[-1])                           # cherry  (-1 = the last one)
print(len(fruits))                          # 3
fruits.append("date")                       # add to the end
print(fruits)

for fruit in fruits:                        # a LOOP: do the same thing for each item
    print("I like", fruit)

for i in range(3):                          # range(3) gives 0, 1, 2
    print("round", i)

total = 0
for n in [1, 2, 3, 4]:
    total = total + n                       # collect a result while looping
print(total)                                # 10

# ---------------- TASKS ----------------
# Task 1: add up all numbers in the list (do it with a loop like above)
def add_all(numbers):
    ...

# Task 2: return a NEW list with only the even numbers
#         hint: start with result = [], loop, use if n % 2 == 0, then result.append(n)
def only_even(numbers):
    ...

from check import check
print("Results:")
check("add_all", add_all([1, 2, 3, 4]), 10)
check("only_even", only_even([1, 2, 3, 4, 5, 6]), [2, 4, 6])
