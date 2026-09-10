# Python program with logic defect: Array index out-of-bounds via range(len(a) + 1)
a = [1, 2, 3, 4, 5]
total = 0

for i in range(len(a) + 1):
    total += a[i]

print("Total:", total)
