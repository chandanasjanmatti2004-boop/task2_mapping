import re

REQUIRED_FIELDS = [
    "loaner_id",
    "fullname",
    "mobile_no",
    "loaner_adhar",
    "total_amount",
    "total_land",
    "descrition"
]

def validate_and_clean(data_list):
    cleaned = []

    for row in data_list:
        clean_row = {}

        for field in REQUIRED_FIELDS:
            clean_row[field] = row.get(field)

        try:
            if clean_row["total_amount"] is not None:
                clean_row["total_amount"] = float(clean_row["total_amount"])
        except:
            clean_row["total_amount"] = None

        if clean_row["mobile_no"]:
            if not re.match(r"^[6-9][0-9]{9}$", str(clean_row["mobile_no"])):
                clean_row["mobile_no"] = None

        if clean_row["loaner_adhar"]:
            if not re.match(r"^[0-9]{12}$", str(clean_row["loaner_adhar"])):
                clean_row["loaner_adhar"] = None

        cleaned.append(clean_row)

    return cleaned