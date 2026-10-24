# LESSON 3 – Decisions (if)
# Run it:   python3 lesson03.py

temperature = 18

if temperature > 25:
    print("hot")                # the 4 spaces in front matter! They say "this belongs to the if"
elif temperature > 15:
    print("nice")
else:
    print("cold")

# Comparisons:  ==  equal   !=  not equal   <  >  <=  >=
# Combine them: and, or, not
age = 20
if age >= 18 and age < 65:
    print("adult at work age")

print(5 == 5, 5 == 6, "a" == "a")      # True False True  (== compares, = stores!)

# ---------------- TASKS ----------------
# Task 1: finish the function: return "even" if n is even, otherwise "odd"
#         (hint: n % 2 == 0 means even)
def even_or_odd(n):
    ...

# Task 2: return "pass" if score is 50 or more, otherwise "fail"
def grade(score):
    ...

from check import check
print("Results:")
check("even_or_odd(4)", even_or_odd(4), "even")
check("even_or_odd(7)", even_or_odd(7), "odd")
check("grade(50)", grade(50), "pass")
check("grade(49)", grade(49), "fail")
# (A function is a named block of code. def name(input): ... return result. More in lesson 6.)
