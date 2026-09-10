# Python program with syntax error (missing colon after function declaration)
def compute_factorial(n)
    if n <= 1:
        return 1
    return n * compute_factorial(n - 1)

print(compute_factorial(5))
