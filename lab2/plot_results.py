import os
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'results.csv')
OUTPUT_IMAGE = os.path.join(os.path.dirname(__file__), 'bandwidth_comparison.png')

def plot_results():
    """
    Reads performance data from results.csv, calculates average bandwidth
    for each controller, and generates a comparative bar plot.
    """
    # --- 1. Data Loading and Validation ---
    if not os.path.exists(RESULTS_FILE):
        print(f"Error: Results file '{RESULTS_FILE}' not found.")
        print("Please run the evaluation script first for each controller.")
        print("Example: sudo ./lab2/evaluation.sh ft_routing")
        return

    try:
        data = pd.read_csv(RESULTS_FILE, header=None, names=['controller', 'bandwidth'])
        if data.empty:
            raise ValueError("The results file is empty.")
    except (pd.errors.EmptyDataError, ValueError) as e:
        print(f"Error: {e}")
        print("Please ensure the evaluation has been run and results.csv contains data.")
        return

    # --- 2. Data Processing ---
    # Clean up controller names for better plot labels
    data['controller'] = data['controller'].str.replace('_', ' ').str.title()
    
    # Calculate average and standard deviation of bandwidth for each controller
    # This provides a more robust comparison if you run the test multiple times
    summary = data.groupby('controller')['bandwidth'].agg(['mean', 'std']).reset_index()
    summary['std'] = summary['std'].fillna(0) # Replace NaN with 0 if only one run

    print("\nPerformance Summary:")
    print(summary)

    # --- 3. Plotting ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 7))

    # Create bars with error bars for standard deviation
    bars = ax.bar(summary['controller'], summary['mean'], 
                  yerr=summary['std'], capsize=5,
                  color=['skyblue', 'salmon', 'lightgreen', 'gold'])

    ax.set_title('Controller Performance Comparison', fontsize=16, weight='bold')
    ax.set_ylabel('Total Aggregate Bandwidth (Mbps)', fontsize=12)
    ax.set_xlabel('Routing Strategy', fontsize=12)
    ax.set_xticklabels(summary['controller'], rotation=0, ha='center')
    ax.margins(y=0.1) # Add some space at the top

    # Add bandwidth values on top of the bars
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + max(summary['std']) * 0.1 + 5, 
                f'{yval:.2f}', ha='center', va='bottom', fontsize=11, weight='bold')

    # --- 4. Save and Show ---
    plt.tight_layout()
    plt.savefig(OUTPUT_IMAGE)
    print(f"\nPlot saved successfully to '{OUTPUT_IMAGE}'")
    plt.show()


if __name__ == '__main__':
    try:
        import pandas
        import matplotlib
    except ImportError:
        print("="*60)
        print("Required Python libraries are not installed.")
        print("Please install them by running the following command:")
        print("\n    pip install pandas matplotlib seaborn\n")
        print("="*60)
    else:
        plot_results() 