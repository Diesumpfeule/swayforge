# LESSON 1 – Printing and variables
# Run it:   python3 lesson01.py
# Read the comments, run the file, then do the TASKS at the bottom.
# Lines starting with # are comments: Python ignores them.

print("Hello!")                 # print() shows something on the screen

name = "Sam"                    # a VARIABLE is a name that holds a value
age = 30
print(name)
print(age)
print("My name is", name)       # print can show several things, separated by commas

age = age + 1                   # you can change a variable: take the old value, add 1
print("Next year:", age)

# ---------------- TASKS (replace the ... with your code) ----------------
# Task 1: make a variable called city with the value "Zurich" (or your own city)
city = ...

# Task 2: make a variable called x with the number 7 and y with the number 5,
#         then make z that holds x + y
x = ...
y = ...
z = ...

from check import check
print("Results:")
check("city is text", isinstance(city, str), True)
check("z is 12", z, 12)
# Bonus: add a line at the end that prints: I live in <your city>
