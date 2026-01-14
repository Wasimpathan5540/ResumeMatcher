import pandas as pd

df = pd.read_csv("jobs.csv")

print("Columns in dataset:")
print(df.columns)

print("\nFirst 5 rows:")
print(df.head())
