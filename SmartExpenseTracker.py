"""
Smart Expense Tracker (single-file)
Features:
- Add / Edit / Delete expenses
- View list of expenses (search by text)
- Monthly summary with pie chart
- Export expenses to CSV
Storage: sqlite3 (local file expenses.db)

Dependencies:
- Python 3.8+
- pandas (optional, for export)
- matplotlib

Install: pip install pandas matplotlib
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date
import os
import sys

# matplotlib embedding
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import pandas as pd
except Exception:
    pd = None  # export will fall back to manual csv writing

DB_FILE = "expenses.db"

DEFAULT_CATEGORIES = [
    "Food", "Transport", "Groceries", "Bills", "Entertainment", "Health",
    "Shopping", "Rent", "Subscriptions", "Misc"
]


class ExpenseDB:
    def __init__(self, db_file=DB_FILE):
        self.conn = sqlite3.connect(db_file)
        self.create_table()

    def create_table(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                note TEXT
            )
            """
        )
        self.conn.commit()

    def add_expense(self, amount, category, date_str, note):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO expenses (amount, category, date, note) VALUES (?, ?, ?, ?)",
            (amount, category, date_str, note),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_expense(self, expense_id, amount, category, date_str, note):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, note = ? WHERE id = ?",
            (amount, category, date_str, note, expense_id),
        )
        self.conn.commit()

    def delete_expense(self, expense_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        self.conn.commit()

    def fetch_expenses(self, search=None, start_date=None, end_date=None):
        cur = self.conn.cursor()
        query = "SELECT id, amount, category, date, note FROM expenses"
        clauses = []
        params = []
        if search:
            clauses.append("(category LIKE ? OR note LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if start_date:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("date <= ?")
            params.append(end_date)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY date DESC, id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows

    def monthly_summary(self, year, month):
        # returns dict category -> total_amount
        cur = self.conn.cursor()
        start = f"{year:04d}-{month:02d}-01"
        # compute end date (next month first day) safely
        if month == 12:
            end = f"{year+1:04d}-01-01"
        else:
            end = f"{year:04d}-{month+1:02d}-01"
        cur.execute(
            "SELECT category, SUM(amount) FROM expenses WHERE date >= ? AND date < ? GROUP BY category",
            (start, end),
        )
        data = dict(cur.fetchall())
        return data


class ExpenseTrackerApp(tk.Tk):
    def __init__(self, db: ExpenseDB):
        super().__init__()
        self.title("Smart Expense Tracker")
        self.geometry("950x600")
        self.db = db
        self.create_widgets()
        self.load_expenses()

    def create_widgets(self):
        # Top frame - add expense
        top = ttk.LabelFrame(self, text="Add Expense", padding=10)
        top.pack(fill="x", padx=10, pady=6)

        ttk.Label(top, text="Amount:").grid(row=0, column=0, sticky="w")
        self.amount_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.amount_var, width=12).grid(row=0, column=1, padx=6, pady=4)

        ttk.Label(top, text="Category:").grid(row=0, column=2, sticky="w")
        self.category_var = tk.StringVar()
        self.category_cb = ttk.Combobox(top, textvariable=self.category_var, values=DEFAULT_CATEGORIES, width=18)
        self.category_cb.set(DEFAULT_CATEGORIES[0])
        self.category_cb.grid(row=0, column=3, padx=6)

        ttk.Label(top, text="Date (YYYY-MM-DD):").grid(row=0, column=4, sticky="w")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(top, textvariable=self.date_var, width=14).grid(row=0, column=5, padx=6)

        ttk.Label(top, text="Note:").grid(row=1, column=0, sticky="w")
        self.note_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.note_var, width=60).grid(row=1, column=1, columnspan=4, sticky="w", padx=6, pady=6)

        ttk.Button(top, text="Add Expense", command=self.add_expense).grid(row=1, column=5, padx=6, sticky="e")

        # Middle frame - controls & search
        middle = ttk.Frame(self)
        middle.pack(fill="x", padx=10, pady=6)

        ttk.Label(middle, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(middle, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<Return>", lambda e: self.load_expenses())
        ttk.Button(middle, text="Search", command=self.load_expenses).pack(side="left", padx=4)
        ttk.Button(middle, text="Clear", command=self.clear_search).pack(side="left", padx=4)

        ttk.Button(middle, text="Export to CSV", command=self.export_csv).pack(side="right")
        ttk.Button(middle, text="Monthly Report", command=self.open_report_window).pack(side="right", padx=8)

        # Bottom frame - expenses list and operations
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=True, padx=10, pady=6)

        # Treeview for list
        cols = ("id", "amount", "category", "date", "note")
        self.tree = ttk.Treeview(bottom, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c.capitalize())
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("amount", width=100, anchor="e")
        self.tree.column("category", width=130, anchor="w")
        self.tree.column("date", width=110, anchor="center")
        self.tree.column("note", width=350, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # scrollbar
        scroll = ttk.Scrollbar(bottom, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        # right-side operations
        ops = ttk.Frame(bottom, width=200)
        ops.pack(side="left", fill="y", padx=10)

        ttk.Button(ops, text="Edit Selected", command=self.edit_selected).pack(fill="x", pady=6)
        ttk.Button(ops, text="Delete Selected", command=self.delete_selected).pack(fill="x", pady=6)
        ttk.Button(ops, text="Refresh", command=self.load_expenses).pack(fill="x", pady=6)

        # status
        self.status_var = tk.StringVar()
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(side="bottom", fill="x")

    def set_status(self, text):
        self.status_var.set(text)

    def clear_search(self):
        self.search_var.set("")
        self.load_expenses()

    def validate_date(self, date_text):
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
            return True
        except Exception:
            return False

    def add_expense(self):
        amt_text = self.amount_var.get().strip()
        cat = self.category_var.get().strip()
        date_text = self.date_var.get().strip()
        note = self.note_var.get().strip()

        if not amt_text:
            messagebox.showwarning("Validation", "Please enter amount.")
            return
        try:
            amt = float(amt_text)
        except ValueError:
            messagebox.showwarning("Validation", "Invalid amount. Use numbers like 250.50")
            return
        if not cat:
            messagebox.showwarning("Validation", "Please select a category.")
            return
        if not self.validate_date(date_text):
            messagebox.showwarning("Validation", "Invalid date format. Use YYYY-MM-DD.")
            return

        eid = self.db.add_expense(amt, cat, date_text, note)
        self.set_status(f"Added expense #{eid}")
        self.amount_var.set("")
        self.note_var.set("")
        self.date_var.set(date.today().isoformat())
        self.load_expenses()

    def load_expenses(self):
        search = self.search_var.get().strip()
        rows = self.db.fetch_expenses(search=search)
        # clear tree
        for r in self.tree.get_children():
            self.tree.delete(r)
        total = 0.0
        for row in rows:
            eid, amount, category, date_str, note = row
            self.tree.insert("", "end", values=(eid, f"{amount:.2f}", category, date_str, note))
            total += float(amount)
        self.set_status(f"Loaded {len(rows)} records — Total: ₹{total:.2f}")

    def get_selected_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select an expense first.")
            return None
        vals = self.tree.item(sel[0], "values")
        # (id, amount, category, date, note)
        return vals

    def on_tree_double_click(self, event):
        self.edit_selected()

    def edit_selected(self):
        vals = self.get_selected_item()
        if not vals:
            return
        eid = int(vals[0])
        amount = vals[1]
        category = vals[2]
        date_str = vals[3]
        note = vals[4] if len(vals) > 4 else ""

        EditExpenseWindow(self, self.db, eid, amount, category, date_str, note, on_save=self.load_expenses)

    def delete_selected(self):
        vals = self.get_selected_item()
        if not vals:
            return
        eid = int(vals[0])
        if messagebox.askyesno("Delete", f"Are you sure you want to delete expense #{eid}?"):
            self.db.delete_expense(eid)
            self.set_status(f"Deleted expense #{eid}")
            self.load_expenses()

    def export_csv(self):
        rows = self.db.fetch_expenses()
        if not rows:
            messagebox.showinfo("Export", "No data to export.")
            return
        default_path = os.path.join(os.getcwd(), f"expenses_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=os.path.basename(default_path),
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        headers = ["id", "amount", "category", "date", "note"]
        try:
            if pd:
                df = pd.DataFrame(rows, columns=headers)
                df.to_csv(path, index=False)
            else:
                # fallback
                with open(path, "w", encoding="utf-8") as f:
                    f.write(",".join(headers) + "\n")
                    for r in rows:
                        # escape commas naively
                        line = ",".join([str(r[0]), f"{r[1]:.2f}", r[2].replace(",", " "), r[3], (r[4] or "").replace(",", " ")])
                        f.write(line + "\n")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")
            return
        messagebox.showinfo("Export", f"Exported {len(rows)} rows to:\n{path}")
        self.set_status(f"Exported {len(rows)} rows to {path}")

    def open_report_window(self):
        ReportWindow(self, self.db)


class EditExpenseWindow(tk.Toplevel):
    def __init__(self, parent, db: ExpenseDB, expense_id, amount, category, date_str, note, on_save=None):
        super().__init__(parent)
        self.title(f"Edit Expense #{expense_id}")
        self.db = db
        self.eid = expense_id
        self.on_save = on_save

        ttk.Label(self, text="Amount:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.amount_var = tk.StringVar(value=str(amount))
        ttk.Entry(self, textvariable=self.amount_var, width=15).grid(row=0, column=1)

        ttk.Label(self, text="Category:").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.category_var = tk.StringVar(value=category)
        cb = ttk.Combobox(self, textvariable=self.category_var, values=DEFAULT_CATEGORIES, width=20)
        cb.grid(row=1, column=1)

        ttk.Label(self, text="Date (YYYY-MM-DD):").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.date_var = tk.StringVar(value=date_str)
        ttk.Entry(self, textvariable=self.date_var, width=15).grid(row=2, column=1)

        ttk.Label(self, text="Note:").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        self.note_var = tk.StringVar(value=note)
        ttk.Entry(self, textvariable=self.note_var, width=50).grid(row=3, column=1)

        ttk.Button(self, text="Save", command=self.save).grid(row=4, column=0, columnspan=2, pady=10)

    def save(self):
        amt_text = self.amount_var.get().strip()
        cat = self.category_var.get().strip()
        date_text = self.date_var.get().strip()
        note = self.note_var.get().strip()

        if not amt_text:
            messagebox.showwarning("Validation", "Please enter amount.")
            return
        try:
            amt = float(amt_text)
        except ValueError:
            messagebox.showwarning("Validation", "Invalid amount.")
            return
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except Exception:
            messagebox.showwarning("Validation", "Invalid date format.")
            return

        self.db.update_expense(self.eid, amt, cat, date_text, note)
        messagebox.showinfo("Saved", f"Expense #{self.eid} updated.")
        if callable(self.on_save):
            self.on_save()
        self.destroy()


class ReportWindow(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.title("Monthly Report")
        self.db = db
        self.geometry("800x500")

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=6)
        today = date.today()
        self.year_var = tk.IntVar(value=today.year)
        self.month_var = tk.IntVar(value=today.month)

        ttk.Label(controls, text="Year:").pack(side="left")
        ttk.Spinbox(controls, from_=2000, to=2100, textvariable=self.year_var, width=6).pack(side="left", padx=6)
        ttk.Label(controls, text="Month:").pack(side="left")
        ttk.Spinbox(controls, from_=1, to=12, textvariable=self.month_var, width=4).pack(side="left", padx=6)
        ttk.Button(controls, text="Show", command=self.show_report).pack(side="left", padx=8)
        ttk.Button(controls, text="Close", command=self.destroy).pack(side="right", padx=8)

        # area for summary & chart
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=6)

        self.summary_text = tk.Text(container, width=40)
        self.summary_text.pack(side="left", fill="y", padx=6, pady=6)

        # matplotlib figure placeholder
        fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(fig, master=container)
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True)

        # initial show
        self.show_report()

    def show_report(self):
        year = self.year_var.get()
        month = self.month_var.get()
        if month < 1 or month > 12:
            messagebox.showwarning("Invalid", "Month must be 1-12.")
            return
        data = self.db.monthly_summary(year, month)
        total = sum(data.values()) if data else 0.0
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, f"Report for {year}-{month:02d}\n")
        self.summary_text.insert(tk.END, "-" * 30 + "\n")
        if not data:
            self.summary_text.insert(tk.END, "No expenses recorded for this month.\n")
            self.ax.clear()
            self.canvas.draw()
            return
        for cat, amt in sorted(data.items(), key=lambda x: -x[1]):
            self.summary_text.insert(tk.END, f"{cat:15s} : ₹{amt:.2f}\n")
        self.summary_text.insert(tk.END, "-" * 30 + "\n")
        self.summary_text.insert(tk.END, f"Total : ₹{total:.2f}\n")

        # pie chart
        self.ax.clear()
        labels = list(data.keys())
        sizes = list(data.values())
        # autopct for percentages
        self.ax.pie(sizes, labels=labels, autopct=lambda p: f"{p:.1f}%\n(₹{p*total/100:.0f})")
        self.ax.set_title(f"Expenses {year}-{month:02d} (Total ₹{total:.2f})")
        self.canvas.draw()


def initialize_db_with_sample_if_empty(db: ExpenseDB):
    rows = db.fetch_expenses()
    if not rows:
        # add a few sample expenses
        today = date.today().isoformat()
        db.add_expense(120.0, "Food", today, "Lunch")
        db.add_expense(400.0, "Transport", today, "Monthly pass")
        db.add_expense(2500.0, "Rent", today, "September rent")


def main():
    db = ExpenseDB()
    # uncomment to preload sample if DB empty
    # initialize_db_with_sample_if_empty(db)
    app = ExpenseTrackerApp(db)
    app.mainloop()


if __name__ == "__main__":
    main()
