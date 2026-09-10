#include <stdio.h>

int main(void) {
    int n = 5;
    int a[5] = {1, 2, 3, 4, 5};

    for(int i = 0; i < n; i++) {
        printf("%d ", a[i]);
    }
    printf("\n");

    return 0;
}
