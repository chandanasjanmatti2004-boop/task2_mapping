import streamlit as st
import requests
import pandas as pd

FASTAPI_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Loaner Pipeline", layout="wide")

st.title("Loaner Data Pipeline")

# ---------------- SIDEBAR ----------------
st.sidebar.title("Pipeline")

step = st.sidebar.radio(
    "Steps",
    [
        "Upload Excel",
        "Database Preview"
    ]
)
#this my first change
# ---------------- UPLOAD steps ----------------
if step == "Upload Excel":

    st.header("Upload Excel File")

    file = st.file_uploader("Upload XLSX file", type=["xlsx"])

    if file is not None:

        if st.button("Send to FastAPI"):

            files = {
                "file": (file.name, file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            }

            response = requests.post(
                f"{FASTAPI_URL}/upload/",
                files=files
            )

            if response.status_code == 200:

                data = response.json()

                st.success("Upload Successful")

                st.write("Rows Inserted:", data["rows_inserted"])
                st.write("Duplicates Skipped:", data["duplicates_skipped"])

                st.subheader("Preview")
                st.json(data["preview"])

            else:
                st.error(response.text)


# ---------------- DATABASE PREVIEW ----------------
elif step == "Database Preview":

    st.header("Loaner Database")

    if st.button("Load Data"):

        response = requests.get(f"{FASTAPI_URL}/loaners")

        if response.status_code == 200:

            data = response.json()

            df = pd.DataFrame(data["data"])

            st.success(f"Total Records: {data['count']}")

            st.dataframe(df)

        else:
            st.error("Could not fetch data")