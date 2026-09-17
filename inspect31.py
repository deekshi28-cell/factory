from readers import read_docx

result = read_docx(r"D:\FactoryKA\documents\6.docx")

# Table 31 was identified earlier as the source for the shipping weight question
table = result['tables'][31]
print(f"Table 31 - {len(table['rows'])} rows total\n")
for i, row in enumerate(table['rows']):
    print(f"Row {i}: {row}")