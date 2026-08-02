import streamlit as st
import pandas as pd

# Give your app a title
st.title("My First Streamlit App! 🎈")

# Add some text
st.write("Welcome to the app. Here is a sample dataset:")

# Create some sample data
data = pd.DataFrame({
    'Category': ['A', 'B', 'C', 'D'],
    'Values': [10, 25, 15, 30]
})

# Display the data as a table
st.dataframe(data)

# Display the data as a chart
st.bar_chart(data, x='Category', y='Values')
