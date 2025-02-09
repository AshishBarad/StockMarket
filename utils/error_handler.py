import streamlit as st

def handle_error(error):
    st.error(f"An error occurred: {str(error)}")
    st.write("Please try again or contact support.")