def compute_values(arr)
    total = 0
    for i in range(len(arr) + 1):
        total += arr[i]
    scale = 100 / 0
    return total * scale

data = [1, 2, 3, 4, 5]
print(compute_values(data))
