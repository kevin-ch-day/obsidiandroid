import pandas as pd
from utils import display_utils as du

def display_dataframe_menu(df_name: str, df: pd.DataFrame) -> str:
    print(f"\n[INSPECT] {df_name} — {df.shape[0]} rows × {df.shape[1]} columns")
    print("-" * 60)
    print("  [1] Head (Top 10 Rows)")
    print("  [2] Summary (describe + dtypes)")
    print("  [3] Info (nulls, schema)")
    print("  [4] Value Counts for Column")
    print("  [5] Column List")
    print("  [6] Show Dimensions")
    print("  [0] Exit Inspection")
    print("-" * 60)
    return input("Select an option: ").strip()


def inspect_dataframe(df: pd.DataFrame, df_name: str = "DataFrame"):
    # Skip pure metadata tables
    if not isinstance(df, pd.DataFrame):
        du.print_error(f"[INSPECT] Object '{df_name}' is not a DataFrame.")
        return

    # Optional: Strip metadata rows before preview
    preview_df = df.copy()
    if preview_df.index.dtype == "object":
        preview_df = preview_df[~preview_df.index.astype(str).str.startswith("meta::")]

    if preview_df.empty:
        du.print_warning(f"[INSPECT] '{df_name}' has no previewable rows (only metadata?).")
        return

    while True:
        du.clear_console()

        choice = display_dataframe_menu(df_name, preview_df)

        if choice == "0":
            print(f"\n[EXIT] Leaving inspection for: {df_name}")
            break

        elif choice == "1":
            du.display_dataframe(preview_df.head(10), title=f"{df_name} – Top Rows")
            input("\nReturn to menu...")

        elif choice == "2":
            desc = preview_df.describe(include='all').transpose()
            du.display_dataframe(desc, title=f"{df_name} – Summary Stats")
            print("\nColumn Types:")
            print(preview_df.dtypes)
            input("\nReturn to menu...")

        elif choice == "3":
            print(f"\n[{df_name}] DataFrame Info:\n")
            preview_df.info()
            input("\nReturn to menu...")

        elif choice == "4":
            column = input("Enter column name to analyze: ").strip()
            if column in preview_df.columns:
                vc = preview_df[column].value_counts(dropna=False).head(20)
                du.display_dataframe(vc.reset_index().rename(columns={"index": column, column: "count"}),
                                     title=f"{df_name} – Value Counts for '{column}'")
            else:
                du.print_warning(f"Column '{column}' not found.")
            input("\nReturn to menu...")

        elif choice == "5":
            du.display_dataframe(pd.DataFrame({"Columns": preview_df.columns.tolist()}),
                                 title=f"{df_name} – Column List")
            input("\nReturn to menu...")

        elif choice == "6":
            print(f"\n[{df_name}] Dimensions:")
            print(f"  Rows   : {preview_df.shape[0]}")
            print(f"  Columns: {preview_df.shape[1]}")
            print(f"  Columns Preview: {', '.join(preview_df.columns[:6])}...")
            input("\nReturn to menu...")

        else:
            du.print_warning("Invalid selection. Choose from menu options.")
            input("\nReturn to menu...")


__all__ = ["inspect_dataframe"]
