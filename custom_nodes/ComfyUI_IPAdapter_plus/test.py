import ast
str = '[[0.1,0.2,0.3,0.4],[0.1,0.2,0.3,0.4]]'

list_data = ast.literal_eval(str)
print(list_data)