import json
import os

def display_metrics(file_name):
    # Load the JSON file
    with open(file_name, 'r') as file:
        data = json.load(file)

    # Display the company name
    company_name = "My Shipping Corp Ltd."
    print(f"Company {company_name}")
    
    # Header
    print("+---------+---------+")
    print("| Name    | Value   |")
    print("+---------+---------+")
    
    # Display company performance summary
    company_data = data.get("companies", {}).get(company_name, {})
    
    # Extract values for Cost, Penalty, Revenue, and calculate Income
    cost = company_data.get("Cost", 0)
    penalty = company_data.get("Penalty", 0)
    revenue = company_data.get("Revenue", 0)
    income = revenue - cost - penalty

    # Print values in table format
    print(f"| Cost    | {cost:<7} |")
    print(f"| Penalty | {penalty:<7} |")
    print(f"| Revenue | {revenue:<7} |")
    print("+---------+---------+")
    print(f"| Income  | {income:<7} |")
    print("+---------+---------+")

if __name__ == "__main__":
    # Find the metrics file
    metrics_file = "metrics_competition_4408627552.json"
    if metrics_file:
        print(f"Found metrics file: {metrics_file}")
        display_metrics(metrics_file)
    else:
        print("No metrics_competition_<number>.json file found in the current directory.")
