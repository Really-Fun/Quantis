from typing import overload


class Matrix:

    def __init__(self, columns: int = 3, rows: int = 4, matrix: list[list] = None) -> None:
        self.columns = columns
        self.rows = rows
        if matrix is not None:
            self.matrix = matrix
        else:
            self.matrix = [[0 for j in range(self.rows)] for i in range(self.columns)]

    @classmethod
    def create_from_matrix(cls, matrix: list[list]):
        if not matrix:
            return Matrix(0, 0)
        columns = len(matrix)
        rows = len(matrix[0])
        return Matrix(columns, rows, matrix)

    def load_values_from_strings(self, values: list[str]) -> None:
        for column in range(self.columns):
            temp_values = values[column].split(" ")
            for row in range(self.rows):
                self.matrix[column][row] = temp_values[row]

    def print(self):
        for column in range(self.columns):
            print("|", end="")
            for row in range(self.rows):
                print(self.matrix[column][row], end=" ")
            print("|")
        print()

matrix1 = Matrix()
matrix2 = Matrix()
matrix3 = Matrix()
matrix4 = Matrix()
matrix5 = Matrix()
matrix6 = Matrix()
matrix7 = Matrix()
matrix1.load_values_from_strings(["2 4 5 3", "3 6 4 2", "4 8 17 11"])
matrix2.load_values_from_strings(["2 2 5 3", "3 3 4 2", "4 4 17 11"])
matrix3.load_values_from_strings(["0 2 5 3", "0 3 4 2", "0 4 17 11"])
matrix4.load_values_from_strings(["0 3 5 2", "0 2 4 3", "0 11 17 4"])
matrix5.load_values_from_strings(["0 1 5 2", "0 -1 4 3", "0 7 17 4"])
matrix6.load_values_from_strings(["0 1 5 2", "0 0 9 5", "0 0 -18 -10"])
matrix7.load_values_from_strings(["0 1 5 2", "0 0 9 5", "0 0 0 0"])

for matrix in [matrix1, matrix2, matrix3, matrix4, matrix5, matrix6, matrix7]:
    matrix.print()