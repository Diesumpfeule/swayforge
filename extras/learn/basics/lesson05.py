# LESSON 5 – Functions and dictionaries
# Run it:   python3 lesson05.py

def double(n):                  # def = "I define a function". n is its input.
    return n * 2                # return = what comes out

print(double(4))                # 8

def greet(name, loud=False):    # loud=False: an optional input with a default
    text = f"Hello {name}"
    if loud:
        text = text.upper()
    return text

print(greet("Sam"))
print(greet("Sam", loud=True))

# A DICTIONARY stores pairs: key -> value (like a phone book)
person = {"name": "Sam", "age": 31}
print(person["name"])           # Sam
person["city"] = "Zurich"       # add a new pair
for key, value in person.items():
    print(key, "=", value)

# ---------------- TASKS ----------------
# Task 1: return the bigger of two numbers (without using max)
def bigger(a, b):
    ...

# Task 2: count how often each letter appears: count_letters("hello") -> {"h":1,"e":1,"l":2,"o":1}
#         hint: result = {}; loop over the text; if letter in result: add 1, else: set it to 1
def count_letters(text):
    ...

from check import check
print("Results:")
check("bigger(3, 9)", bigger(3, 9), 9)
check("bigger(10, 2)", bigger(10, 2), 10)
check("count_letters", count_letters("hello"), {"h": 1, "e": 1, "l": 2, "o": 1})
