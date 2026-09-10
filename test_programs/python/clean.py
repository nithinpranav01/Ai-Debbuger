# Clean, error-free Python program
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

if __name__ == '__main__':
    data = [10, 20, 30, 40, 50]
    result = calculate_sum(data)
    print("Calculated Sum:", result)
