# Exact SQL execution errors by example and table

Tested **381 original SQL answers** with SQLite 3.50.4 (Python 3.14.7); `PRAGMA foreign_keys=ON`.

**315 succeed; 66 fail.** A separate scan attempts all 1748 unchanged CREATE statements and finds **115 failing statements** across those 66 examples.

Here, an example is one dataset row/schema. Each entry below gives its 1-based JSONL source line, ID, failing statement/table, and exact SQLite message. SQL line numbers refer to the decoded `answer` string, not the physical JSONL file.

The original whole-script run stops at its first error. The separate statement scan continues after a failed CREATE, preserving earlier successful tables; later failures are additional diagnostics that the original run never reaches. Both runs use fresh in-memory databases per example. No SQL is repaired, no rows are inserted, and successful CREATE statements are not a proof of valid foreign-key behavior or normalization.

Each failed execution reports SQLite's first error for that statement. Further defects inside the same CREATE statement can remain hidden. The failing-statement count does not count every possible defect in the source.

SQLite supplies no error line/column through this Python exception API; the ranges below identify the complete failing statement. Error messages, including multiline messages, are preserved without truncation. For malformed apostrophes, the whole-script error can include SQL following the first failed statement, while the statement-only message ends at its boundary.

## Files and reproduction

- [schemas.csv](schemas.csv): all examples, including successful ones and the first whole-script error.
- [statements.csv](statements.csv): all CREATE statements, their exact SQL, status and error.
- [errors.jsonl](errors.jsonl): only failures, grouped by example, including original and statement errors.
- [summary.json](summary.json): counts, source checksum and runtime.

From the repository root:

```bash
python3 dataset-analysis/RSchema/scripts/inspect_sql_execution.py
```

## Failing examples: first error in the original script

| Source line | ID | First failed table | Statement | Exact error (single-line messages) |
|---:|---|---|---:|---|
| [5](#example-5) | `67552f0a13602ec03b41a7aa` | `Maintenance_Record` | 4 | `no such column: Device_ID` |
| [12](#example-12) | `67552f0a13602ec03b41a7ba` | `Order` | 3 | `near "Order": syntax error` |
| [15](#example-15) | `67552f0a13602ec03b41a7c7` | `Inventory` | 3 | `near "-": syntax error` |
| [35](#example-35) | `67552f0a13602ec03b41a81e` | `Supply_Record` | 3 | `no such column: Record_ID` |
| [51](#example-51) | `67552f0a13602ec03b41a85b` | `Order` | 3 | `near "Order": syntax error` |
| [54](#example-54) | `67552f0a13602ec03b41a864` | `user` | 2 | `near "-": syntax error` |
| [61](#example-61) | `67552f0a13602ec03b41a881` | `Transaction` | 3 | `near "Transaction": syntax error` |
| [63](#example-63) | `67552f0a13602ec03b41a885` | `attendance` | 4 | `near "-": syntax error` |
| [70](#example-70) | `67552f0a13602ec03b41a8b5` | `Order` | 3 | `near "Order": syntax error` |
| [74](#example-74) | `67552f0a13602ec03b41a8c7` | `Add_Contact` | 3 | `no such column: Adding_time` |
| [78](#example-78) | `67552f0a13602ec03b41a8e9` | `Update` | 2 | `near "Update": syntax error` |
| [80](#example-80) | `67552f0a13602ec03b41a8f3` | `Order` | 3 | `near "Order": syntax error` |
| [83](#example-83) | `67552f0a13602ec03b41a913` | `employee_attendance` | 2 | `no such column: clock` |
| [93](#example-93) | `67552f0a13602ec03b41a987` | `Order` | 3 | `near "Order": syntax error` |
| [111](#example-111) | `67552f0b13602ec03b41aa40` | `Order` | 4 | `near "Order": syntax error` |
| [118](#example-118) | `67552f0b13602ec03b41aa9c` | `Order` | 3 | `near "Order": syntax error` |
| [124](#example-124) | `67552f0b13602ec03b41aacb` | `Directory` | 2 | `near "-": syntax error` |
| [125](#example-125) | `67552f0b13602ec03b41aadb` | `Order` | 6 | `near "Order": syntax error` |
| [126](#example-126) | `67552f0b13602ec03b41ab2b` | `Order` | 3 | `near "Order": syntax error` |
| [137](#example-137) | `67552f0a13602ec03b41a7e5` | `Sales_Record` | 4 | `no such column: Employee_ID` |
| [141](#example-141) | `67552f0a13602ec03b41a7f7` | `Order` | 2 | `near "Order": syntax error` |
| [151](#example-151) | `67552f0a13602ec03b41a849` | `Transaction` | 4 | `near "Transaction": syntax error` |
| [154](#example-154) | `67552f0a13602ec03b41a875` | `Order` | 6 | `near "Order": syntax error` |
| [159](#example-159) | `67552f0a13602ec03b41a8a9` | `Order` | 5 | `near "Order": syntax error` |
| [160](#example-160) | `67552f0a13602ec03b41a8ae` | `Order` | 7 | `near "Order": syntax error` |
| [161](#example-161) | `67552f0a13602ec03b41a8cc` | `Order` | 2 | `near "Order": syntax error` |
| [164](#example-164) | `67552f0a13602ec03b41a90d` | `Order` | 4 | `near "Order": syntax error` |
| [172](#example-172) | `67552f0a13602ec03b41a9be` | `Order` | 4 | `near "Order": syntax error` |
| [175](#example-175) | `67552f0a13602ec03b41a9f5` | `Comment` | 4 | `no such column: Information_ID` |
| [176](#example-176) | `67552f0a13602ec03b41a9f9` | `Sign-in` | 3 | `near "-": syntax error` |
| [179](#example-179) | `67552f0b13602ec03b41aa28` | `Order` | 3 | `near "Order": syntax error` |
| [181](#example-181) | `67552f0b13602ec03b41aa35` | `Two-Player_Battle_Game` | 5 | `near "-": syntax error` |
| [185](#example-185) | `67552f0b13602ec03b41aaa9` | `Customer` | 1 | `near "-": syntax error` |
| [194](#example-194) | `67552f0a13602ec03b41a796` | `Table` | 1 | `near "Table": syntax error` |
| [197](#example-197) | `67552f0a13602ec03b41a7b2` | `Entry/Exit_Records` | 6 | `near "/": syntax error` |
| [218](#example-218) | `67552f0a13602ec03b41a84a` | `Transaction` | 3 | `near "Transaction": syntax error` |
| [233](#example-233) | `67552f0a13602ec03b41a8ac` | `Order` | 6 | `near "Order": syntax error` |
| [236](#example-236) | `67552f0a13602ec03b41a8b1` | `E-book` | 3 | `near "-": syntax error` |
| [244](#example-244) | `67552f0a13602ec03b41a8d7` | `Order` | 4 | `near "Order": syntax error` |
| [252](#example-252) | `67552f0a13602ec03b41a8f0` | `Order` | 4 | `near "Order": syntax error` |
| [273](#example-273) | `67552f0a13602ec03b41a941` | `Order` | 3 | `near "Order": syntax error` |
| [276](#example-276) | `67552f0a13602ec03b41a94d` | `User_Account` | 2 | `near "-": syntax error` |
| [294](#example-294) | `67552f0a13602ec03b41a99a` | `patient` | 1 | `(multiline; full message below)` |
| [295](#example-295) | `67552f0a13602ec03b41a99f` | `Order` | 4 | `near "Order": syntax error` |
| [298](#example-298) | `67552f0a13602ec03b41a9af` | `Table` | 2 | `near "Table": syntax error` |
| [304](#example-304) | `67552f0a13602ec03b41a9d4` | `Order` | 4 | `near "Order": syntax error` |
| [308](#example-308) | `67552f0a13602ec03b41a9f3` | `User_Table` | 1 | `(multiline; full message below)` |
| [311](#example-311) | `67552f0a13602ec03b41aa02` | `Order` | 3 | `near "Order": syntax error` |
| [325](#example-325) | `67552f0b13602ec03b41aa44` | `Order` | 4 | `near "Order": syntax error` |
| [327](#example-327) | `67552f0b13602ec03b41aa49` | `Device` | 1 | `near "Group": syntax error` |
| [329](#example-329) | `67552f0b13602ec03b41aa52` | `Attendance_Record` | 4 | `near "-": syntax error` |
| [333](#example-333) | `67552f0b13602ec03b41aaa6` | `Stock-out_notification` | 7 | `near "-": syntax error` |
| [334](#example-334) | `67552f0b13602ec03b41aaa7` | `Order` | 4 | `near "Order": syntax error` |
| [336](#example-336) | `67552f0b13602ec03b41aab5` | `Order` | 4 | `near "Order": syntax error` |
| [337](#example-337) | `67552f0b13602ec03b41aab6` | `Order` | 3 | `near "Order": syntax error` |
| [342](#example-342) | `67552f0b13602ec03b41aad7` | `Order` | 3 | `near "Order": syntax error` |
| [344](#example-344) | `67552f0b13602ec03b41aae9` | `Order` | 4 | `near "Order": syntax error` |
| [347](#example-347) | `67552f0b13602ec03b41aaf9` | `Order` | 4 | `near "Order": syntax error` |
| [353](#example-353) | `67552f0b13602ec03b41ab4a` | `Maintenance_Task` | 5 | `near "-": syntax error` |
| [358](#example-358) | `67552f0a13602ec03b41a8e1` | `Order` | 3 | `near "Order": syntax error` |
| [360](#example-360) | `67552f0a13602ec03b41a951` | `attendance_record` | 4 | `near "Check": syntax error` |
| [362](#example-362) | `67552f0a13602ec03b41a98b` | `Transaction` | 3 | `near "Transaction": syntax error` |
| [371](#example-371) | `67552f0b13602ec03b41aa95` | `Order` | 3 | `near "Order": syntax error` |
| [375](#example-375) | `67552f0b13602ec03b41ab03` | `Transaction` | 3 | `near "Transaction": syntax error` |
| [377](#example-377) | `67552f0b13602ec03b41ab15` | `Transaction` | 3 | `near "Transaction": syntax error` |
| [379](#example-379) | `67552f0b13602ec03b41ab2c` | `Income/Expenditure` | 4 | `near "/": syntax error` |

## Exact details for every failing example

<a id="example-5"></a>

### Example 5: `67552f0a13602ec03b41a7aa`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 5. First failure: statement 4, table `Maintenance_Record`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: Device_ID
```

**Statement 4: `Maintenance_Record` (SQL lines 24-33).** First failure in the original run.

Exact statement error:

```text
no such column: Device_ID
```

Unmodified failing statement:

```sql
CREATE TABLE Maintenance_Record (
    Equipment_ID INTEGER NOT NULL,
    Maintenance_Date DATETIME,
    Maintenance_Result VARCHAR(255),
    Maintenance_Type VARCHAR(255),
    Operator_ID INTEGER NOT NULL,
    PRIMARY KEY (Device_ID, Operator_ID, Maintenance_Date),
    FOREIGN KEY (Equipment_ID) REFERENCES Equipment(Equipment_ID),
    FOREIGN KEY (Operator_ID) REFERENCES Operator(Operator_ID)
);
```

<a id="example-12"></a>

### Example 12: `67552f0a13602ec03b41a7ba`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 12. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 13-20).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_status VARCHAR(255),
    Order_time DATETIME,
    Total_amount INTEGER,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 4: `Order_Details` (SQL lines 22-29).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Details (
    Dish_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, Dish_ID),
    FOREIGN KEY (Dish_ID) REFERENCES Dish(Dish_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-15"></a>

### Example 15: `67552f0a13602ec03b41a7c7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 15. First failure: statement 3, table `Inventory`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 3: `Inventory` (SQL lines 16-22).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Inventory (
    Inventory_ID INTEGER PRIMARY KEY,
    Quantity VARCHAR(255),
    Stock-in_Time DATETIME,
    Textile_ID INTEGER NOT NULL,
    FOREIGN KEY (Textile_ID) REFERENCES Textile(Textile_ID)
);
```

<a id="example-35"></a>

### Example 35: `67552f0a13602ec03b41a81e`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 35. First failure: statement 3, table `Supply_Record`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: Record_ID
```

**Statement 3: `Supply_Record` (SQL lines 15-23).** First failure in the original run.

Exact statement error:

```text
no such column: Record_ID
```

Unmodified failing statement:

```sql
CREATE TABLE Supply_Record (
    Operator_ID INTEGER NOT NULL,
    Supply_Date DATETIME,
    Supply_Quantity INTEGER,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (User_ID, Record_ID, Supply_Date),
    FOREIGN KEY (Operator_ID) REFERENCES Operator(Operator_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-51"></a>

### Example 51: `67552f0a13602ec03b41a85b`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 51. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 21-27).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Delivery_Status VARCHAR(255),
    Order_ID INTEGER PRIMARY KEY,
    Purchase_Date DATETIME,
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(ID)
);
```

**Statement 5: `Order_Detail` (SQL lines 38-45).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Detail (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Purchase_Quantity INTEGER,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-54"></a>

### Example 54: `67552f0a13602ec03b41a864`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 54. First failure: statement 2, table `user`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 2: `user` (SQL lines 7-21).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE user (
    activation_status VARCHAR(255),
    creator VARCHAR(255),
    email VARCHAR(255),
    last_updated_time DATETIME,
    one-time_password VARCHAR(255),
    password VARCHAR(255),
    password_reset_key VARCHAR(255),
    updater VARCHAR(255),
    user_allocation_time DATETIME,
    user_group_id INTEGER NOT NULL,
    user_id INTEGER PRIMARY KEY,
    username VARCHAR(255),
    FOREIGN KEY (user_group_id) REFERENCES user_group(user_group_id)
);
```

<a id="example-61"></a>

### Example 61: `67552f0a13602ec03b41a881`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 61. First failure: statement 3, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 3: `Transaction` (SQL lines 15-25).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Block_Hash VARCHAR(255) NOT NULL,
    Fee FLOAT,
    Input_Address VARCHAR(255) NOT NULL,
    Output_Address VARCHAR(255) NOT NULL,
    Timestamp DATETIME,
    Transaction_Hash VARCHAR(255) PRIMARY KEY,
    FOREIGN KEY (Block_Hash) REFERENCES Block(Block_Hash),
    FOREIGN KEY (Input_Address) REFERENCES Account(Address),
    FOREIGN KEY (Output_Address) REFERENCES Account(Address)
);
```

<a id="example-63"></a>

### Example 63: `67552f0a13602ec03b41a885`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 63. First failure: statement 4, table `attendance`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 4: `attendance` (SQL lines 26-33).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE attendance (
    attendance_date DATETIME,
    attendance_id INTEGER PRIMARY KEY,
    check-in_and_check-out_times DATETIME,
    employee_id INTEGER NOT NULL,
    whether_late_or_early_departure VARCHAR(255),
    FOREIGN KEY (employee_id) REFERENCES employee(employee_id)
);
```

<a id="example-70"></a>

### Example 70: `67552f0a13602ec03b41a8b5`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 70. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 20-34).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Creation_Time DATETIME,
    Creator_User_ID INTEGER NOT NULL,
    Currency_Type VARCHAR(255),
    Customer_ID INTEGER NOT NULL,
    Deletion_Time DATETIME,
    Delivery_Date DATETIME,
    Invoice_Number VARCHAR(255),
    Order_Description VARCHAR(255),
    Order_ID INTEGER PRIMARY KEY,
    Order_Number VARCHAR(255),
    Update_Time DATETIME,
    FOREIGN KEY (Creator_User_ID) REFERENCES User(User_ID),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 5: `Order_Item` (SQL lines 49-60).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Item (
    Creation_Time DATETIME,
    Deletion_Time DATETIME,
    Description VARCHAR(255),
    Order_ID INTEGER NOT NULL,
    Order_Item_ID INTEGER PRIMARY KEY,
    Quantity INTEGER,
    Unit VARCHAR(255),
    Unit_Price FLOAT,
    Update_Time DATETIME,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-74"></a>

### Example 74: `67552f0a13602ec03b41a8c7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 74. First failure: statement 3, table `Add_Contact`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: Adding_time
```

**Statement 3: `Add_Contact` (SQL lines 24-33).** First failure in the original run.

Exact statement error:

```text
no such column: Adding_time
```

Unmodified failing statement:

```sql
CREATE TABLE Add_Contact (
    Add_Time DATETIME,
    Added_User_ID INTEGER NOT NULL,
    Relationship_Type VARCHAR(255),
    Remarks VARCHAR(255),
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (User_ID, Added_User_ID, Adding_time),
    FOREIGN KEY (Added_User_ID) REFERENCES User(User_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 4: `Social_Activity` (SQL lines 35-45).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
no such column: User_Dynamic_ID
```

Unmodified failing statement:

```sql
CREATE TABLE Social_Activity (
    Collection BOOL,
    Comment VARCHAR(255),
    Creation_Time DATETIME,
    Dynamic_ID INTEGER NOT NULL,
    Like BOOL,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (User_ID, User_Dynamic_ID, Creation_Time),
    FOREIGN KEY (Dynamic_ID) REFERENCES User_dynamic_information(Dynamic_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-78"></a>

### Example 78: `67552f0a13602ec03b41a8e9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 78. First failure: statement 2, table `Update`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Update": syntax error
```

**Statement 2: `Update` (SQL lines 12-19).** First failure in the original run.

Exact statement error:

```text
near "Update": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Update (
    Content VARCHAR(255),
    Content_Type VARCHAR(255),
    Posting_Time DATETIME,
    Update_ID INTEGER PRIMARY KEY,
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 4: `Comment` (SQL lines 30-38).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Update": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Comment (
    Comment_Content VARCHAR(255),
    Comment_ID INTEGER PRIMARY KEY,
    Comment_Time DATETIME,
    Commenter_ID INTEGER NOT NULL,
    Update_ID INTEGER NOT NULL,
    FOREIGN KEY (Commenter_ID) REFERENCES User(User_ID),
    FOREIGN KEY (Update_ID) REFERENCES Update(Update_ID)
);
```

<a id="example-80"></a>

### Example 80: `67552f0a13602ec03b41a8f3`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 80. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 28-36).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Actual_shipping_date DATETIME,
    Notes VARCHAR(255),
    Order_ID INTEGER PRIMARY KEY,
    Order_date DATETIME,
    Order_status VARCHAR(255),
    Required_delivery_date DATETIME,
    Special_instructions VARCHAR(255)
);
```

**Statement 5: `Customer` (SQL lines 50-64).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "/": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Customer (
    City VARCHAR(255),
    Contact_person_name VARCHAR(255),
    Contact_person_phone VARCHAR(255),
    Contact_person_position VARCHAR(255),
    Country VARCHAR(255),
    Credit_limit FLOAT,
    Customer_ID INTEGER PRIMARY KEY,
    Customer_company_name VARCHAR(255),
    Dedicated_sales_rep_employee_ID INTEGER NOT NULL,
    Postal_code VARCHAR(255),
    State/Province VARCHAR(255),
    Street VARCHAR(255),
    FOREIGN KEY (Dedicated_sales_rep_employee_ID) REFERENCES Employee(Employee_ID)
);
```

**Statement 7: `Order_detail` (SQL lines 74-83).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_detail (
    Line_number VARCHAR(255),
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Unit_price FLOAT,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-83"></a>

### Example 83: `67552f0a13602ec03b41a913`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 83. First failure: statement 2, table `employee_attendance`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: clock
```

**Statement 2: `employee_attendance` (SQL lines 10-15).** First failure in the original run.

Exact statement error:

```text
no such column: clock
```

Unmodified failing statement:

```sql
CREATE TABLE employee_attendance (
    employee_ID INTEGER,
    punch_time DATETIME,
    punch_type VARCHAR(255),
    PRIMARY KEY (employee_ID, clock-in_time)
);
```

**Statement 4: `employee_transfer_department` (SQL lines 31-40).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE employee_transfer_department (
    employee_ID INTEGER NOT NULL,
    transfer_time DATETIME,
    transfer-in_department_ID INTEGER NOT NULL,
    transfer-out_department_ID INTEGER NOT NULL,
    PRIMARY KEY (employee_ID, transfer_time),
    FOREIGN KEY (employee_ID) REFERENCES employee(employee_ID),
    FOREIGN KEY (transfer-in_department_ID) REFERENCES department(department_ID),
    FOREIGN KEY (transfer-out_department_ID) REFERENCES department(department_ID)
);
```

<a id="example-93"></a>

### Example 93: `67552f0a13602ec03b41a987`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 93. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 16-25).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Amount_Paid FLOAT,
    Order_Number INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Payment_Time DATETIME,
    Shipping_Address VARCHAR(255),
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-111"></a>

### Example 111: `67552f0b13602ec03b41aa40`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 111. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 23-30).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Ordering_User INTEGER NOT NULL,
    Update_Time DATETIME,
    FOREIGN KEY (Ordering_User) REFERENCES User(User_ID)
);
```

**Statement 6: `Order_Details` (SQL lines 41-49).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Details (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Unit_Price FLOAT,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-118"></a>

### Example 118: `67552f0b13602ec03b41aa9c`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 118. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 23-31).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Member_ID INTEGER NOT NULL,
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Points FLOAT,
    Sales_Amount FLOAT,
    Shipping_Date DATETIME,
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID)
);
```

**Statement 4: `Order_Detail` (SQL lines 33-39).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Detail (
    Book_ID INTEGER PRIMARY KEY NOT NULL,
    Order_ID INTEGER NOT NULL,
    Sales_Quantity INTEGER,
    FOREIGN KEY (Book_ID) REFERENCES Book(Book_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-124"></a>

### Example 124: `67552f0b13602ec03b41aacb`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 124. First failure: statement 2, table `Directory`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 2: `Directory` (SQL lines 9-14).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Directory (
    Directory_ID INTEGER PRIMARY KEY,
    File_ID INTEGER NOT NULL,
    Sub-file/directory_list BLOB,
    FOREIGN KEY (File_ID) REFERENCES Abstract_File(File_ID)
);
```

<a id="example-125"></a>

### Example 125: `67552f0b13602ec03b41aadb`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 125. First failure: statement 6, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 6: `Order` (SQL lines 48-58).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Mailing_Address VARCHAR(255),
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time FLOAT,
    Prescription_ID INTEGER NOT NULL,
    Total_Price FLOAT,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Prescription_ID) REFERENCES Prescription_Medication_Association(Prescription_ID)
);
```

<a id="example-126"></a>

### Example 126: `67552f0b13602ec03b41ab2b`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 126. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 15-22).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Expected_Delivery_Date DATETIME,
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 4: `Ordered_Pizza` (SQL lines 24-31).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Ordered_Pizza (
    Order_ID INTEGER NOT NULL,
    Pizza_ID INTEGER NOT NULL,
    Pizza_Quantity INTEGER,
    PRIMARY KEY (Order_ID, Pizza_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Pizza_ID) REFERENCES Pizza(Pizza_ID)
);
```

<a id="example-137"></a>

### Example 137: `67552f0a13602ec03b41a7e5`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 137. First failure: statement 4, table `Sales_Record`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: Employee_ID
```

**Statement 4: `Sales_Record` (SQL lines 23-33).** First failure in the original run.

Exact statement error:

```text
no such column: Employee_ID
```

Unmodified failing statement:

```sql
CREATE TABLE Sales_Record (
    Client_ID INTEGER NOT NULL,
    Property_ID INTEGER NOT NULL,
    Sale_Date DATETIME,
    Sale_Price FLOAT,
    Sales_Personnel_ID INTEGER NOT NULL,
    PRIMARY KEY (Property_ID, Employee_ID, Client_ID),
    FOREIGN KEY (Client_ID) REFERENCES Client(Client_ID),
    FOREIGN KEY (Property_ID) REFERENCES Property(Property_ID),
    FOREIGN KEY (Sales_Personnel_ID) REFERENCES Sales_Personnel(Employee_ID)
);
```

<a id="example-141"></a>

### Example 141: `67552f0a13602ec03b41a7f7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 141. First failure: statement 2, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 2: `Order` (SQL lines 9-15).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_Time DATETIME,
    Total_Price FLOAT,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 4: `Order_Detail` (SQL lines 23-29).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Detail (
    Order_Detail_ID INTEGER PRIMARY KEY,
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER,
    Quantity INTEGER,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-151"></a>

### Example 151: `67552f0a13602ec03b41a849`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 151. First failure: statement 4, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 4: `Transaction` (SQL lines 24-34).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Card_Number VARCHAR(255) NOT NULL,
    Customer_ID INTEGER NOT NULL,
    Transaction_Amount FLOAT,
    Transaction_Location VARCHAR(255),
    Transaction_Time DATETIME,
    Transaction_Type VARCHAR(255),
    PRIMARY KEY (Customer_ID, Card_Number, Transaction_Time),
    FOREIGN KEY (Card_Number) REFERENCES Credit_Card(Card_Number),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

<a id="example-154"></a>

### Example 154: `67552f0a13602ec03b41a875`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 154. First failure: statement 6, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 6: `Order` (SQL lines 39-51).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_Price FLOAT,
    Payment_Method VARCHAR(255),
    Postal_Code INTEGER NOT NULL,
    Shipping_Method VARCHAR(255),
    Tax FLOAT,
    Total_Price FLOAT,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Postal_Code) REFERENCES Address(Postal_Code)
);
```

**Statement 7: `Order_Detail` (SQL lines 53-60).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Detail (
    Detail_ID INTEGER PRIMARY KEY,
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-159"></a>

### Example 159: `67552f0a13602ec03b41a8a9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 159. First failure: statement 5, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 5: `Order` (SQL lines 29-39).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Book_ID INTEGER NOT NULL,
    Branch_ID INTEGER NOT NULL,
    Customer_ID INTEGER NOT NULL,
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Purchase_Quantity INTEGER,
    FOREIGN KEY (Book_ID) REFERENCES Book(Book_ID),
    FOREIGN KEY (Branch_ID) REFERENCES Branch(Branch_ID),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

<a id="example-160"></a>

### Example 160: `67552f0a13602ec03b41a8ae`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 160. First failure: statement 7, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 7: `Order` (SQL lines 56-65).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Handler VARCHAR(255),
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Priority VARCHAR(255),
    Total_Price FLOAT,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 8: `Order_Composed_of_Products` (SQL lines 67-83).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Composed_of_Products (
    Discount FLOAT,
    Extended_Price FLOAT,
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Receipt_Date DATETIME,
    Return_Indicator VARCHAR(255),
    Shipment_Date DATETIME,
    Shipping_Instructions VARCHAR(255),
    Shipping_Method VARCHAR(255),
    Status VARCHAR(255),
    Tax FLOAT,
    PRIMARY KEY (Order_ID, Product_ID, Shipment_Date),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-161"></a>

### Example 161: `67552f0a13602ec03b41a8cc`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 161. First failure: statement 2, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 2: `Order` (SQL lines 10-17).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_Content VARCHAR(255),
    Order_Creation_Time DATETIME,
    Order_ID INTEGER PRIMARY KEY NOT NULL,
    FOREIGN KEY (Customer_ID) REFERENCES Customer_Information(Customer_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 3: `Customer_Payment_Order` (SQL lines 19-29).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Customer_Payment_Order (
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Payment_Amount FLOAT,
    Payment_Method VARCHAR(255),
    Payment_Status VARCHAR(255),
    Payment_Time DATETIME,
    PRIMARY KEY (Customer_ID, Order_ID, Payment_Time),
    FOREIGN KEY (Customer_ID) REFERENCES Customer_Information(Customer_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-164"></a>

### Example 164: `67552f0a13602ec03b41a90d`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 164. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 38-45).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Creation_Time DATETIME,
    Customer_ID INTEGER NOT NULL,
    Deletion_Time DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Update_Time DATETIME,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 5: `Order_and_Product` (SQL lines 47-54).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_and_Product (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-172"></a>

### Example 172: `67552f0a13602ec03b41a9be`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 172. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 23-30).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Employee_ID INTEGER NOT NULL,
    Member_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_Time DATETIME,
    FOREIGN KEY (Employee_ID) REFERENCES Employee(Employee_ID),
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID)
);
```

<a id="example-175"></a>

### Example 175: `67552f0a13602ec03b41a9f5`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 175. First failure: statement 4, table `Comment`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
no such column: Information_ID
```

**Statement 4: `Comment` (SQL lines 25-33).** First failure in the original run.

Exact statement error:

```text
no such column: Information_ID
```

Unmodified failing statement:

```sql
CREATE TABLE Comment (
    Comment_Content VARCHAR(255),
    Comment_Time DATETIME,
    Film_ID INTEGER NOT NULL,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (Information_ID, User_ID, Comment_Time),
    FOREIGN KEY (Film_ID) REFERENCES Film_Information(Information_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-176"></a>

### Example 176: `67552f0a13602ec03b41a9f9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 176. First failure: statement 3, table `Sign-in`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 3: `Sign-in` (SQL lines 18-25).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Sign-in (
    IP_Address VARCHAR(255),
    Sign-in_Status VARCHAR(255),
    Sign-in_Time DATETIME,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (User_ID, Sign-in_Time),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 5: `Control_Flag` (SQL lines 35-41).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Control_Flag (
    Sign-in_End_Time DATETIME,
    Sign-in_Start_Time DATETIME,
    Teacher_ID INTEGER NOT NULL,
    PRIMARY KEY (Teacher_ID, Sign-in_Start_Time),
    FOREIGN KEY (Teacher_ID) REFERENCES User(User_ID)
);
```

<a id="example-179"></a>

### Example 179: `67552f0b13602ec03b41aa28`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 179. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 21-30).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Delivery_Address VARCHAR(255),
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Payment_Time DATETIME,
    Total_Amount FLOAT,
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 6: `Order_Product` (SQL lines 51-60).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Product (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Subtotal FLOAT,
    Unit_Price FLOAT,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

**Statement 7: `User_Order` (SQL lines 62-73).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE User_Order (
    Delivery_Address VARCHAR(255),
    Order_ID INTEGER NOT NULL,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Payment_Time DATETIME,
    Total_Amount FLOAT,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (Order_ID, User_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 8: `Admin_Order_Management` (SQL lines 75-83).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Admin_Order_Management (
    Admin_ID INTEGER NOT NULL,
    Operation_Time DATETIME,
    Operation_Type VARCHAR(255),
    Order_ID INTEGER NOT NULL,
    PRIMARY KEY (Admin_ID, Order_ID),
    FOREIGN KEY (Admin_ID) REFERENCES User(User_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-181"></a>

### Example 181: `67552f0b13602ec03b41aa35`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 181. First failure: statement 5, table `Two-Player_Battle_Game`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 5: `Two-Player_Battle_Game` (SQL lines 39-50).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Two-Player_Battle_Game (
    Battle_End_Time DATETIME,
    Battle_Result VARCHAR(255),
    Battle_Start_Time DATETIME,
    First_Player_ID INTEGER NOT NULL,
    Game_ID INTEGER NOT NULL,
    Second_Player_ID INTEGER NOT NULL,
    PRIMARY KEY (First_Player_ID, Second_Player_ID, Game_ID, Battle_Start_Time),
    FOREIGN KEY (First_Player_ID) REFERENCES Player(Player_ID),
    FOREIGN KEY (Game_ID) REFERENCES Game_Record(Game_ID),
    FOREIGN KEY (Second_Player_ID) REFERENCES Player(Player_ID)
);
```

<a id="example-185"></a>

### Example 185: `67552f0b13602ec03b41aaa9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 185. First failure: statement 1, table `Customer`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 1: `Customer` (SQL lines 1-11).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Customer (
    Customer_Booking_Date DATETIME,
    Customer_Check-in_Time DATETIME,
    Customer_Check-out_Time DATETIME,
    Customer_Contact_Information VARCHAR(255),
    Customer_Gender VARCHAR(255),
    Customer_ID INTEGER PRIMARY KEY,
    Customer_ID_Number INTEGER,
    Customer_Name VARCHAR(255),
    Customer_Type VARCHAR(255)
);
```

**Statement 4: `Order` (SQL lines 33-41).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Discount_Rate FLOAT,
    Order_Flight_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Ticket_Order_Number INTEGER,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Order_Flight_ID) REFERENCES Flight(Flight_ID)
);
```

<a id="example-194"></a>

### Example 194: `67552f0a13602ec03b41a796`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 194. First failure: statement 1, table `Table`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Table": syntax error
```

**Statement 1: `Table` (SQL lines 1-5).** First failure in the original run.

Exact statement error:

```text
near "Table": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Table (
    Location VARCHAR(255),
    Seating_Capacity INTEGER,
    Table_ID INTEGER PRIMARY KEY
);
```

**Statement 3: `Reservation` (SQL lines 13-22).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Table": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Reservation (
    Customer_ID INTEGER NOT NULL,
    Number_of_Diners INTEGER,
    Reservation_Status VARCHAR(255),
    Reservation_Time DATETIME,
    Table_ID INTEGER NOT NULL,
    PRIMARY KEY (Customer_ID, Table_ID, Reservation_Time),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Table_ID) REFERENCES Table(Table_ID)
);
```

<a id="example-197"></a>

### Example 197: `67552f0a13602ec03b41a7b2`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 197. First failure: statement 6, table `Entry/Exit_Records`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "/": syntax error
```

**Statement 6: `Entry/Exit_Records` (SQL lines 40-46).** First failure in the original run.

Exact statement error:

```text
near "/": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Entry/Exit_Records (
    Entry/Exit_Type VARCHAR(255),
    Livestock_ID INTEGER NOT NULL,
    Time DATETIME,
    PRIMARY KEY (Livestock_ID, Time),
    FOREIGN KEY (Livestock_ID) REFERENCES Livestock(Livestock_ID)
);
```

<a id="example-218"></a>

### Example 218: `67552f0a13602ec03b41a84a`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 218. First failure: statement 3, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 3: `Transaction` (SQL lines 16-27).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Client_ID INTEGER NOT NULL,
    Futures_Code VARCHAR(255),
    Trader_ID INTEGER NOT NULL,
    Transaction_Price FLOAT,
    Transaction_Quantity INTEGER,
    Transaction_Time DATETIME,
    Transaction_Type VARCHAR(255),
    PRIMARY KEY (Trader_ID, Client_ID, Futures_Code),
    FOREIGN KEY (Client_ID) REFERENCES Client(Client_ID),
    FOREIGN KEY (Trader_ID) REFERENCES Trader(Trader_ID)
);
```

<a id="example-233"></a>

### Example 233: `67552f0a13602ec03b41a8ac`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 233. First failure: statement 6, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 6: `Order` (SQL lines 32-46).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Credit_Card_Expiry_Date DATETIME,
    Credit_Card_Number INTEGER,
    Credit_Card_Security_Code VARCHAR(255),
    Mexican_Tortilla_ID INTEGER NOT NULL,
    Order_Creation_Time DATETIME,
    Recipient VARCHAR(255) NOT NULL,
    Recipient_City VARCHAR(255),
    Recipient_Postal_Code INTEGER,
    Recipient_State/Province VARCHAR(255),
    Recipient_Street_Address VARCHAR(255),
    PRIMARY KEY (Mexican_Tortilla_ID, Order_Creation_Time, Recipient),
    FOREIGN KEY (Mexican_Tortilla_ID) REFERENCES Mexican_Tortilla_Design(Mexican_Tortilla_ID),
    FOREIGN KEY (Recipient) REFERENCES User(Username)
);
```

<a id="example-236"></a>

### Example 236: `67552f0a13602ec03b41a8b1`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 236. First failure: statement 3, table `E-book`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 3: `E-book` (SQL lines 15-22).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE E-book (
    Book_title VARCHAR(255),
    Category_ID INTEGER NOT NULL,
    Cover_URL VARCHAR(255),
    Detailed_description VARCHAR(255),
    E-book_ID INTEGER PRIMARY KEY,
    FOREIGN KEY (Category_ID) REFERENCES Category(Category_ID)
);
```

**Statement 4: `Document` (SQL lines 24-29).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Document (
    Document_ID INTEGER PRIMARY KEY,
    Document_content VARCHAR(255),
    E-book_ID INTEGER NOT NULL,
    FOREIGN KEY (E-book_ID) REFERENCES E-book(E-book_ID)
);
```

**Statement 5: `Statistics` (SQL lines 31-38).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Statistics (
    Date DATETIME,
    E-book_ID INTEGER NOT NULL,
    Like_count INTEGER,
    Read_count INTEGER,
    Statistics_ID INTEGER PRIMARY KEY,
    FOREIGN KEY (E-book_ID) REFERENCES E-book(E-book_ID)
);
```

<a id="example-244"></a>

### Example 244: `67552f0a13602ec03b41a8d7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 244. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 27-37).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Amount FLOAT,
    Currency VARCHAR(255),
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Resource_ID INTEGER NOT NULL,
    Start_Time DATETIME,
    Type VARCHAR(255),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Resource_ID) REFERENCES Resource(Resource_ID)
);
```

<a id="example-252"></a>

### Example 252: `67552f0a13602ec03b41a8f0`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 252. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 32-42).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Creation_Time DATETIME,
    Delivery_Address DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Postal_Code VARCHAR(255),
    Total_Order_Price FLOAT,
    Update_Time DATETIME,
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 5: `Order_Contains_Product` (SQL lines 44-51).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Contains_Product (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Product_Quantity INTEGER,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-273"></a>

### Example 273: `67552f0a13602ec03b41a941`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 273. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 18-24).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_Time DATETIME,
    Status VARCHAR(255),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 4: `Order_Item` (SQL lines 26-33).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Item (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-276"></a>

### Example 276: `67552f0a13602ec03b41a94d`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 276. First failure: statement 2, table `User_Account`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 2: `User_Account` (SQL lines 11-23).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE User_Account (
    Access_Token VARCHAR(255),
    Access_Token_Expiration_Time DATETIME,
    Account_Creation_Time DATETIME,
    Account_ID INTEGER PRIMARY KEY,
    Account_Update_Time DATETIME,
    Refresh_Token VARCHAR(255),
    Third-party_Service_Provider_Account_ID INTEGER,
    Third-party_Service_Provider_ID INTEGER,
    Third-party_Service_Provider_Type VARCHAR(255),
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-294"></a>

### Example 294: `67552f0a13602ec03b41a99a`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 294. First failure: statement 1, table `patient`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
unrecognized token: "'s_treatment_information VARCHAR(255),
    registration_category_ID INTEGER,
    ward_ID INTEGER
);

CREATE TABLE ward (
    ward_ID INTEGER PRIMARY KEY,
    ward_information VARCHAR(255)
);

CREATE TABLE registration_category (
    registration_category_ID INTEGER PRIMARY KEY,
    registration_information VARCHAR(255)
);

CREATE TABLE drug (
    drug_ID INTEGER PRIMARY KEY,
    drug_information VARCHAR(255)
);

CREATE TABLE prescription (
    drug_ID INTEGER NOT NULL,
    patient_ID INTEGER NOT NULL,
    PRIMARY KEY (drug_ID, patient_ID),
    FOREIGN KEY (drug_ID) REFERENCES drug(drug_ID),
    FOREIGN KEY (patient_ID) REFERENCES patient(patient_ID)
);"
```

**Statement 1: `patient` (SQL lines 1-10).** First failure in the original run.

Exact statement error:

```text
unrecognized token: "'s_treatment_information VARCHAR(255),
    registration_category_ID INTEGER,
    ward_ID INTEGER
);"
```

Unmodified failing statement:

```sql
CREATE TABLE patient (
    age INTEGER,
    contact_information VARCHAR(255),
    gender BOOL,
    name VARCHAR(255),
    patient_ID INTEGER PRIMARY KEY,
    patient's_treatment_information VARCHAR(255),
    registration_category_ID INTEGER,
    ward_ID INTEGER
);
```

<a id="example-295"></a>

### Example 295: `67552f0a13602ec03b41a99f`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 295. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 27-38).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Creation_Time DATETIME,
    Menu_ID INTEGER NOT NULL,
    Order_Amount FLOAT,
    Order_Modification_Time DATETIME,
    Order_Status VARCHAR(255),
    Remarks VARCHAR(255),
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (User_ID, Menu_ID, Creation_Time),
    FOREIGN KEY (Menu_ID) REFERENCES Menu(Menu_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-298"></a>

### Example 298: `67552f0a13602ec03b41a9af`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 298. First failure: statement 2, table `Table`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Table": syntax error
```

**Statement 2: `Table` (SQL lines 8-11).** First failure in the original run.

Exact statement error:

```text
near "Table": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Table (
    Seat_Number INTEGER,
    Table_ID INTEGER PRIMARY KEY
);
```

**Statement 5: `Order` (SQL lines 28-33).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Dining_Time DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Service_Employee_ID INTEGER NOT NULL,
    FOREIGN KEY (Service_Employee_ID) REFERENCES Employee(Employee_ID)
);
```

**Statement 6: `Dish_Table_Order` (SQL lines 35-43).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Dish_Table_Order (
    Dish_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Table_ID INTEGER NOT NULL,
    PRIMARY KEY (Dish_ID, Order_ID, Table_ID),
    FOREIGN KEY (Dish_ID) REFERENCES Menu(Dish_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Table_ID) REFERENCES Table(Table_ID)
);
```

**Statement 7: `Customer_Order` (SQL lines 45-52).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Customer_Order (
    Customer_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Order_Review BOOL,
    PRIMARY KEY (Customer_ID, Order_ID),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-304"></a>

### Example 304: `67552f0a13602ec03b41a9d4`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 304. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 23-29).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Order_Number VARCHAR(255) PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Ordering_User INTEGER NOT NULL,
    FOREIGN KEY (Ordering_User) REFERENCES User(User_ID)
);
```

**Statement 6: `Order_Details` (SQL lines 40-47).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Details (
    Order_Number VARCHAR(255) NOT NULL,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_Number, Product_ID),
    FOREIGN KEY (Order_Number) REFERENCES Order(Order_Number),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-308"></a>

### Example 308: `67552f0a13602ec03b41a9f3`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 308. First failure: statement 1, table `User_Table`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
unrecognized token: "'s_Last_Login DATETIME,
    User_ID INTEGER PRIMARY KEY,
    User_IP_Address VARCHAR(255),
    User_Port_Number INTEGER,
    Username VARCHAR(255)
);

CREATE TABLE Server_Configuration_Table (
    Maximum_Client_Connections INTEGER,
    Protocol_Used VARCHAR(255),
    Receive_Buffer_Size INTEGER,
    Server_ID INTEGER PRIMARY KEY,
    Server_IP_Address VARCHAR(255),
    Server_Port_Number INTEGER
);

CREATE TABLE Chat_Record_Table (
    Message_Content_and_Sending_Time VARCHAR(255),
    Message_ID INTEGER PRIMARY KEY,
    Receiver_ID INTEGER NOT NULL,
    Sender_ID INTEGER NOT NULL,
    User_ID INTEGER,
    FOREIGN KEY (Receiver_ID) REFERENCES User_Table(User_ID),
    FOREIGN KEY (Sender_ID) REFERENCES User_Table(User_ID)
);"
```

**Statement 1: `User_Table` (SQL lines 1-9).** First failure in the original run.

Exact statement error:

```text
unrecognized token: "'s_Last_Login DATETIME,
    User_ID INTEGER PRIMARY KEY,
    User_IP_Address VARCHAR(255),
    User_Port_Number INTEGER,
    Username VARCHAR(255)
);"
```

Unmodified failing statement:

```sql
CREATE TABLE User_Table (
    Email VARCHAR(255),
    Password VARCHAR(255),
    Time_of_User's_Last_Login DATETIME,
    User_ID INTEGER PRIMARY KEY,
    User_IP_Address VARCHAR(255),
    User_Port_Number INTEGER,
    Username VARCHAR(255)
);
```

<a id="example-311"></a>

### Example 311: `67552f0a13602ec03b41aa02`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 311. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 24-31).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Delivery_address VARCHAR(255),
    Delivery_person VARCHAR(255),
    Delivery_time DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_status VARCHAR(255),
    Order_time DATETIME
);
```

**Statement 5: `Order_detail` (SQL lines 44-53).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_detail (
    Dish_ID INTEGER NOT NULL,
    Dish_quantity INTEGER,
    Order_ID INTEGER NOT NULL,
    Total_amount FLOAT,
    Unit_price FLOAT,
    PRIMARY KEY (Dish_ID, Order_ID),
    FOREIGN KEY (Dish_ID) REFERENCES Dish(Dish_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-325"></a>

### Example 325: `67552f0b13602ec03b41aa44`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 325. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 27-37).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Total_Price FLOAT,
    User_ID INTEGER NOT NULL,
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 5: `User_and_Order` (SQL lines 39-51).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE User_and_Order (
    Order_ID INTEGER NOT NULL,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Total_Price FLOAT,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (Order_ID, User_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

**Statement 6: `Order_and_Product` (SQL lines 53-65).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_and_Product (
    Order_ID INTEGER NOT NULL,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Product_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Total_Price FLOAT,
    User_ID INTEGER NOT NULL,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID),
    FOREIGN KEY (User_ID) REFERENCES User(User_ID)
);
```

<a id="example-327"></a>

### Example 327: `67552f0b13602ec03b41aa49`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 327. First failure: statement 1, table `Device`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Group": syntax error
```

**Statement 1: `Device` (SQL lines 1-15).** First failure in the original run.

Exact statement error:

```text
near "Group": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Device (
    Creation_Time DATETIME,
    Department VARCHAR(255),
    Device_ID INTEGER PRIMARY KEY,
    Device_Image BLOB,
    Device_Model VARCHAR(255),
    Group VARCHAR(255),
    IP_Address VARCHAR(255),
    Person_in_Charge VARCHAR(255),
    Product_Name VARCHAR(255),
    QR_Code BLOB,
    Type VARCHAR(255),
    Update_Time DATETIME,
    Usage_Location VARCHAR(255)
);
```

<a id="example-329"></a>

### Example 329: `67552f0b13602ec03b41aa52`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 329. First failure: statement 4, table `Attendance_Record`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 4: `Attendance_Record` (SQL lines 27-37).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Attendance_Record (
    Attendance_Status VARCHAR(255),
    Check-in_Time DATETIME,
    Class_Time DATETIME,
    Course_ID INTEGER NOT NULL,
    Remarks VARCHAR(255),
    Student_ID INTEGER NOT NULL,
    PRIMARY KEY (Student_ID, Course_ID, Check-in_Time),
    FOREIGN KEY (Course_ID) REFERENCES Course(Course_ID),
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID)
);
```

<a id="example-333"></a>

### Example 333: `67552f0b13602ec03b41aaa6`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 333. First failure: statement 7, table `Stock-out_notification`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 7: `Stock-out_notification` (SQL lines 49-54).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Stock-out_notification (
    Notification_ID INTEGER PRIMARY KEY,
    Stock-out_date DATETIME,
    Supply_request_ID INTEGER NOT NULL,
    FOREIGN KEY (Supply_request_ID) REFERENCES Supply_request(Request_ID)
);
```

<a id="example-334"></a>

### Example 334: `67552f0b13602ec03b41aaa7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 334. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 30-36).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Member_ID INTEGER NOT NULL,
    Order_Date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Shipping_Date DATETIME,
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID)
);
```

**Statement 5: `Order_Detail` (SQL lines 38-45).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Detail (
    Book_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, Book_ID),
    FOREIGN KEY (Book_ID) REFERENCES Book(Book_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-336"></a>

### Example 336: `67552f0b13602ec03b41aab5`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 336. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 29-37).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Delivery_Address VARCHAR(255),
    Order_Creation_Time DATETIME,
    Order_Number INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Total_Order_Price FLOAT,
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 5: `Order_Product` (SQL lines 39-46).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Product (
    Order_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Product_Quantity INTEGER,
    PRIMARY KEY (Order_ID, Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_Number),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

**Statement 6: `Order_Delivery` (SQL lines 48-55).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Delivery (
    Delivery_Personnel_ID INTEGER NOT NULL,
    Estimated_Delivery_Time DATETIME,
    Order_ID INTEGER NOT NULL,
    PRIMARY KEY (Order_ID, Delivery_Personnel_ID),
    FOREIGN KEY (Delivery_Personnel_ID) REFERENCES Delivery_Personnel(Delivery_Personnel_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_Number)
);
```

<a id="example-337"></a>

### Example 337: `67552f0b13602ec03b41aab6`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 337. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 23-30).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Member_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_date DATETIME,
    Sales_amount FLOAT,
    Shipping_date DATETIME,
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID)
);
```

**Statement 4: `Purchase` (SQL lines 32-39).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Purchase (
    ISBN VARCHAR(255) NOT NULL,
    Order_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, ISBN),
    FOREIGN KEY (ISBN) REFERENCES Book(ISBN),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-342"></a>

### Example 342: `67552f0b13602ec03b41aad7`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 342. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 14-19).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Order_ID INTEGER PRIMARY KEY,
    Order_Status VARCHAR(255),
    Ordering_Customer_ID INTEGER NOT NULL,
    FOREIGN KEY (Ordering_Customer_ID) REFERENCES Customer(Customer_ID)
);
```

**Statement 4: `Ordered_Product` (SQL lines 21-28).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Ordered_Product (
    Order_ID INTEGER NOT NULL,
    Ordered_Product_ID INTEGER NOT NULL,
    Ordered_Quantity INTEGER,
    PRIMARY KEY (Order_ID, Ordered_Product_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Ordered_Product_ID) REFERENCES Product(Product_ID)
);
```

**Statement 5: `Picking_List` (SQL lines 30-35).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Picking_List (
    Order_ID INTEGER NOT NULL,
    Picking_List_ID INTEGER PRIMARY KEY,
    Picking_Status VARCHAR(255),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 6: `Delivery_Order` (SQL lines 37-42).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Delivery_Order (
    Delivery_Order_ID INTEGER PRIMARY KEY NOT NULL,
    Delivery_Status VARCHAR(255),
    Delivery_Time DATETIME,
    FOREIGN KEY (Delivery_Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 7: `Customer_Invoice` (SQL lines 44-50).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Customer_Invoice (
    Customer_Invoice_ID INTEGER PRIMARY KEY,
    Invoice_Amount FLOAT,
    Invoice_Date DATETIME,
    Order_ID INTEGER NOT NULL,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 8: `Accounts_Receivable_Report` (SQL lines 52-58).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Accounts_Receivable_Report (
    Order_ID INTEGER NOT NULL,
    Receivable_Amount FLOAT,
    Report_Date DATETIME,
    Report_ID INTEGER PRIMARY KEY,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-344"></a>

### Example 344: `67552f0b13602ec03b41aae9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 344. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 22-30).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Delivery_Address VARCHAR(255),
    Delivery_Time DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_Payment_Method VARCHAR(255),
    Order_Total_Price FLOAT,
    Ordering_Employee INTEGER NOT NULL,
    FOREIGN KEY (Ordering_Employee) REFERENCES Enterprise_Employee(Employee_ID)
);
```

**Statement 5: `Order_Dish` (SQL lines 32-39).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_Dish (
    Dish_ID INTEGER NOT NULL,
    Dish_Quantity INTEGER,
    Order_ID INTEGER NOT NULL,
    PRIMARY KEY (Order_ID, Dish_ID),
    FOREIGN KEY (Dish_ID) REFERENCES Menu(Dish_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 6: `Delivery_Record` (SQL lines 41-48).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Delivery_Record (
    Delivery_Order_ID INTEGER NOT NULL,
    Delivery_Record_ID INTEGER PRIMARY KEY,
    Delivery_Time DATETIME,
    Responsible_Delivery_Person_ID INTEGER NOT NULL,
    FOREIGN KEY (Delivery_Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Responsible_Delivery_Person_ID) REFERENCES Delivery_Person(Delivery_Person_ID)
);
```

**Statement 7: `Payment_Request` (SQL lines 50-58).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Payment_Request (
    Paying_Employee_ID INTEGER NOT NULL,
    Paying_Order_ID INTEGER NOT NULL,
    Payment_Request_ID INTEGER PRIMARY KEY,
    Request_Payment_Amount FLOAT,
    Request_Payment_Status VARCHAR(255),
    FOREIGN KEY (Paying_Employee_ID) REFERENCES Enterprise_Employee(Employee_ID),
    FOREIGN KEY (Paying_Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-347"></a>

### Example 347: `67552f0b13602ec03b41aaf9`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 347. First failure: statement 4, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 4: `Order` (SQL lines 26-36).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER NOT NULL,
    Order_Status VARCHAR(255),
    Order_Time DATETIME,
    Payment_Method VARCHAR(255),
    Publication_ID INTEGER NOT NULL,
    Shipping_Address VARCHAR(255),
    PRIMARY KEY (Customer_ID, Publication_ID, Order_Time),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID),
    FOREIGN KEY (Publication_ID) REFERENCES Publication(Publication_ID)
);
```

<a id="example-353"></a>

### Example 353: `67552f0b13602ec03b41ab4a`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 353. First failure: statement 5, table `Maintenance_Task`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "-": syntax error
```

**Statement 5: `Maintenance_Task` (SQL lines 37-45).** First failure in the original run.

Exact statement error:

```text
near "-": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Maintenance_Task (
    License_Plate_Number VARCHAR(255) NOT NULL,
    Maintenance_Content VARCHAR(255),
    Maintenance_Man-Hours FLOAT,
    Maintenance_Order_Number VARCHAR(255) PRIMARY KEY,
    Maintenance_Worker_Number VARCHAR(255) NOT NULL,
    FOREIGN KEY (License_Plate_Number) REFERENCES Vehicle(License_Plate_Number),
    FOREIGN KEY (Maintenance_Worker_Number) REFERENCES Employee(Employee_Number)
);
```

<a id="example-358"></a>

### Example 358: `67552f0a13602ec03b41a8e1`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 358. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 15-21).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Customer_ID INTEGER,
    Delivery_date DATETIME,
    Order_ID INTEGER PRIMARY KEY,
    Order_status VARCHAR(255),
    Order_time DATETIME
);
```

**Statement 6: `Order_detail` (SQL lines 47-58).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_detail (
    Order_ID INTEGER NOT NULL,
    Order_detail_ID INTEGER PRIMARY KEY,
    Part_ID INTEGER NOT NULL,
    Quantity INTEGER,
    Supplier_ID INTEGER NOT NULL,
    Total_amount INTEGER,
    Unit_price FLOAT,
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID),
    FOREIGN KEY (Part_ID) REFERENCES Part(Part_ID),
    FOREIGN KEY (Supplier_ID) REFERENCES Supplier(Supplier_ID)
);
```

<a id="example-360"></a>

### Example 360: `67552f0a13602ec03b41a951`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 360. First failure: statement 4, table `attendance_record`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Check": syntax error
```

**Statement 4: `attendance_record` (SQL lines 28-35).** First failure in the original run.

Exact statement error:

```text
near "Check": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE attendance_record (
    Check-in_Location VARCHAR(255),
    Check-in_Time DATETIME,
    Employee_ID INTEGER NOT NULL,
    Remarks INTEGER,
    PRIMARY KEY (Employee_ID, Check-in_Time),
    FOREIGN KEY (Employee_ID) REFERENCES employee(Employee_ID)
);
```

**Statement 5: `to-do_item` (SQL lines 37-45).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "to": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE to-do_item (
    Completion_Status VARCHAR(255),
    Creation_Time DATETIME,
    Employee_ID INTEGER NOT NULL,
    Task_Description VARCHAR(255),
    Update_Time DATETIME,
    PRIMARY KEY (Employee_ID, Creation_Time),
    FOREIGN KEY (Employee_ID) REFERENCES employee(Employee_ID)
);
```

<a id="example-362"></a>

### Example 362: `67552f0a13602ec03b41a98b`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 362. First failure: statement 3, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 3: `Transaction` (SQL lines 29-41).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Buyer_ID INTEGER NOT NULL,
    Product_ID INTEGER NOT NULL,
    Transaction_amount FLOAT,
    Transaction_evaluation VARCHAR(255),
    Transaction_location VARCHAR(255),
    Transaction_method VARCHAR(255),
    Transaction_status VARCHAR(255),
    Transaction_time DATETIME,
    PRIMARY KEY (Buyer_ID, Product_ID, Transaction_time),
    FOREIGN KEY (Buyer_ID) REFERENCES User(User_ID),
    FOREIGN KEY (Product_ID) REFERENCES Product(Product_ID)
);
```

<a id="example-371"></a>

### Example 371: `67552f0b13602ec03b41aa95`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 371. First failure: statement 3, table `Order`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Order": syntax error
```

**Statement 3: `Order` (SQL lines 24-31).** First failure in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order (
    Member_ID INTEGER NOT NULL,
    Order_ID INTEGER PRIMARY KEY,
    Order_date DATETIME,
    Sales_amount INTEGER,
    Shipping_date DATETIME,
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID)
);
```

**Statement 4: `Order_book` (SQL lines 33-40).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Order_book (
    Book_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    Quantity INTEGER,
    PRIMARY KEY (Order_ID, Book_ID),
    FOREIGN KEY (Book_ID) REFERENCES Book(Book_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

**Statement 5: `Place_order` (SQL lines 42-48).** Additional failure found by continuing; not reached in the original run.

Exact statement error:

```text
near "Order": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Place_order (
    Member_ID INTEGER NOT NULL,
    Order_ID INTEGER NOT NULL,
    PRIMARY KEY (Member_ID, Order_ID),
    FOREIGN KEY (Member_ID) REFERENCES Member(Member_ID),
    FOREIGN KEY (Order_ID) REFERENCES Order(Order_ID)
);
```

<a id="example-375"></a>

### Example 375: `67552f0b13602ec03b41ab03`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 375. First failure: statement 3, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 3: `Transaction` (SQL lines 15-23).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Account_Number VARCHAR(255) NOT NULL,
    Transaction_Amount FLOAT,
    Transaction_ID INTEGER PRIMARY KEY,
    Transaction_Status VARCHAR(255),
    Transaction_Time DATETIME,
    Transaction_Type VARCHAR(255),
    FOREIGN KEY (Account_Number) REFERENCES Account(Account_Number)
);
```

<a id="example-377"></a>

### Example 377: `67552f0b13602ec03b41ab15`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 377. First failure: statement 3, table `Transaction`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "Transaction": syntax error
```

**Statement 3: `Transaction` (SQL lines 16-24).** First failure in the original run.

Exact statement error:

```text
near "Transaction": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Transaction (
    Customer_ID INTEGER NOT NULL,
    Transaction_Amount INTEGER,
    Transaction_ID INTEGER PRIMARY KEY,
    Transaction_Status VARCHAR(255),
    Transaction_Time DATETIME,
    Transaction_Type VARCHAR(255),
    FOREIGN KEY (Customer_ID) REFERENCES Customer(Customer_ID)
);
```

<a id="example-379"></a>

### Example 379: `67552f0b13602ec03b41ab2c`

Source: `dataset/RSchema/annotation_ddl.jsonl`, physical line 379. First failure: statement 4, table `Income/Expenditure`. SQLite code: `SQLITE_ERROR` (1).

**Exact original whole-script error:**

```text
near "/": syntax error
```

**Statement 4: `Income/Expenditure` (SQL lines 23-31).** First failure in the original run.

Exact statement error:

```text
near "/": syntax error
```

Unmodified failing statement:

```sql
CREATE TABLE Income/Expenditure (
    Amount FLOAT,
    Description VARCHAR(255),
    Pizza_ID INTEGER NOT NULL,
    Record_ID INTEGER PRIMARY KEY,
    Time DATETIME,
    Type VARCHAR(255),
    FOREIGN KEY (Pizza_ID) REFERENCES Pizza(Pizza_ID)
);
```
