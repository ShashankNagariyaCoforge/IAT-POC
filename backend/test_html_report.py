from utils.pii_report import generate_case_pii_report

mock_original = "John Doe (dob 01/01/1980) has an email john.doe@example.com."
mock_masked = "[PERSON_1] (dob [DATE_TIME_1]) has an email [EMAIL_ADDRESS_1]."
mock_mappings = [
    {"pii_type": "Person", "original_value": "John Doe", "masked_value": "[PERSON_1]"},
    {"pii_type": "DateTime", "original_value": "01/01/1980", "masked_value": "[DATE_TIME_1]"},
    {"pii_type": "Email", "original_value": "john.doe@example.com", "masked_value": "[EMAIL_ADDRESS_1]"},
]

generate_case_pii_report("TEST-MOCK-HTML", mock_original, mock_masked, mock_mappings)
print("Mock report generated!")
