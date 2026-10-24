# LESSON 2 – Text and numbers
# Run it:   python3 lesson02.py

word = "python"
print(word.upper())             # PYTHON      (. means: "do this to the text")
print(word.capitalize())        # Python
print(len(word))                # 6           (len = how many characters)
print(word + "!")               # python!     (+ glues texts together)
print(word * 3)                 # pythonpythonpython

# f-strings put variables inside text. Put an f before the quote and {} around the variable.
name = "Sam"
age = 31
print(f"{name} is {age} years old")

# Numbers
print(7 + 2, 7 - 2, 7 * 2)      # 9 5 14
print(7 / 2)                    # 3.5   (normal division)
print(7 // 2)                   # 3     (division without the decimals)
print(7 % 2)                    # 1     (the remainder: 7 = 3*2 + 1)
print(2 ** 3)                   # 8     (2 to the power of 3)

# ---------------- TASKS ----------------
# Task 1: make "shout" from the text "hello" so it becomes "HELLO!"  (use upper and +)
shout = ...

# Task 2: use an f-string so greeting is exactly: "Hi Sam, you are 31"
greeting = ...

# Task 3: how many whole 5s fit into 47?  (use //)  and what is left over?  (use %)
fives = ...
rest = ...

from check import check
print("Results:")
check("shout", shout, "HELLO!")
check("greeting", greeting, "Hi Sam, you are 31")
check("fives", fives, 9)
check("rest", rest, 2)
