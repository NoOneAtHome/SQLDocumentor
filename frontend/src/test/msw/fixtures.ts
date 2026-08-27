/**
 * AdventureWorks-flavoured fixture snapshot used by the MSW handlers.
 *
 * The data is deliberately small but shaped like a real `[Sales, dbo]` scan of
 * AdventureWorks2022: in-scope Sales objects, cascaded Person/Production objects, one
 * external (linked-server) node, catalog/FK/trigger edges, and column-level edges with
 * exact / inferred / unresolved confidences.
 */
import type {
  Annotation,
  CheckConstraint,
  Confidence,
  EdgeKind,
  ExecStats,
  Index,
  LineageIssue,
  MissingIndex,
  ObjectKind,
  ObjectScope,
  Parameter,
  Resolution,
  ScanSummary,
  TableStats,
  Transform,
} from '@/api/types'

export const CONNECTION = 'local-aw'
export const DB = 'AdventureWorks2022'
export const SELECTED_SCHEMAS = ['Sales', 'dbo']

export interface FixtureColumn {
  name: string
  type: string
  nullable?: boolean
  identity?: boolean
  computed?: string
  default?: string
  pk?: boolean
  fk?: [objectId: number, column: string]
  desc?: string
}

export interface FixtureObject {
  id: number
  db: string
  schema: string
  name: string
  kind: ObjectKind
  scope: ObjectScope
  description?: string
  modified_at?: string
  created_at?: string
  columns: FixtureColumn[]
  definition?: string
  parent_id?: number
  external?: { server: string; database: string }
  trigger?: { events: string[]; is_instead_of: boolean; is_disabled: boolean }
  params?: Parameter[]
  indexes?: Index[]
  unique?: Array<{ name: string; columns: string[] }>
  checks?: CheckConstraint[]
  stats?: TableStats | ExecStats | null
  missing_indexes?: MissingIndex[]
  lineage_issues?: LineageIssue[]
  lineage_status?: 'ok' | 'partial' | 'failed' | 'skipped' | 'n/a'
  has_dynamic_sql?: boolean
}

export interface FixtureEdge {
  source: number
  target: number
  kind: EdgeKind
  resolution?: Resolution
  detail?: string
}

export interface FixtureColumnEdge {
  s: [objectId: number, column: string]
  t: [objectId: number, column: string]
  confidence: Confidence
  transform: Transform
  via?: number
  expression?: string
}

const STATS_AS_OF = '2026-08-26T09:12:44Z'
const SERVER_START = '2026-08-01T04:00:00Z'

function tableStats(rows: number, dataKb: number, indexKb: number, extra: Partial<TableStats> = {}): TableStats {
  return {
    row_count: rows,
    data_kb: dataKb,
    index_kb: indexKb,
    reserved_kb: dataKb + indexKb + 64,
    partition_count: 1,
    is_heap: false,
    compression: 'NONE',
    stats_as_of: STATS_AS_OF,
    ...extra,
    kind: 'table',
  }
}

function execStats(count: number, avgMs: number, extra: Partial<ExecStats> = {}): ExecStats {
  const total = count * avgMs
  return {
    exec_count: count,
    total_ms: total,
    avg_ms: avgMs,
    min_ms: avgMs * 0.4,
    max_ms: avgMs * 6.5,
    total_cpu_ms: total * 0.7,
    last_exec_at: '2026-08-26T08:58:03Z',
    cached_since: '2026-08-20T12:00:00Z',
    since_server_start: SERVER_START,
    total_logical_reads: count * 40,
    ...extra,
    kind: 'exec',
  }
}

function idx(
  id: number,
  name: string,
  key: string[],
  o: Partial<Index> & { usage?: Index['usage'] } = {},
): Index {
  return {
    id,
    name,
    type_desc: o.type_desc ?? 'NONCLUSTERED',
    is_unique: o.is_unique ?? false,
    is_primary_key: o.is_primary_key ?? false,
    is_unique_constraint: o.is_unique_constraint ?? false,
    key_columns: key.map((k) => ({ name: k, desc: false })),
    included_columns: o.included_columns ?? [],
    filter: o.filter ?? null,
    is_disabled: false,
    usage: o.usage ?? { seeks: 0, scans: 0, lookups: 0, updates: 0 },
    is_unused: o.is_unused ?? false,
    description: o.description ?? null,
  }
}

const AUDIT: FixtureColumn[] = [
  { name: 'rowguid', type: 'uniqueidentifier', default: '(newid())', desc: 'ROWGUIDCOL number uniquely identifying the record. Used to support a merge replication sample.' },
  { name: 'ModifiedDate', type: 'datetime', default: '(getdate())', desc: 'Date and time the record was last updated.' },
]

export const OBJECTS: FixtureObject[] = [
  {
    id: 1, db: DB, schema: 'Sales', name: 'SalesOrderHeader', kind: 'table', scope: 'in_scope',
    description: 'General sales order information.',
    modified_at: '2024-02-11T10:14:00Z', created_at: '2017-10-27T14:33:00Z',
    columns: [
      { name: 'SalesOrderID', type: 'int', identity: true, pk: true, desc: 'Primary key.' },
      { name: 'RevisionNumber', type: 'tinyint', default: '((0))', desc: 'Incremental number to track changes to the sales order over time.' },
      { name: 'OrderDate', type: 'datetime', default: '(getdate())', desc: 'Dates the sales order was created.' },
      { name: 'DueDate', type: 'datetime', desc: 'Date the order is due to the customer.' },
      { name: 'ShipDate', type: 'datetime', nullable: true, desc: 'Date the order was shipped to the customer.' },
      { name: 'Status', type: 'tinyint', default: '((1))', desc: 'Order current status. 1 = In process; 2 = Approved; 3 = Backordered; 4 = Rejected; 5 = Shipped; 6 = Cancelled' },
      { name: 'OnlineOrderFlag', type: 'bit', default: '((1))' },
      { name: 'SalesOrderNumber', type: 'nvarchar(25)', computed: "(isnull(N'SO'+CONVERT([nvarchar](23),[SalesOrderID]),N'*** ERROR ***'))", desc: 'Unique sales order identification number.' },
      { name: 'PurchaseOrderNumber', type: 'nvarchar(25)', nullable: true },
      { name: 'AccountNumber', type: 'nvarchar(15)', nullable: true },
      { name: 'CustomerID', type: 'int', fk: [2, 'CustomerID'], desc: 'Customer identification number. Foreign key to Customer.BusinessEntityID.' },
      { name: 'SalesPersonID', type: 'int', nullable: true, fk: [14, 'BusinessEntityID'] },
      { name: 'TerritoryID', type: 'int', nullable: true, fk: [20, 'TerritoryID'] },
      { name: 'BillToAddressID', type: 'int', fk: [6, 'AddressID'] },
      { name: 'ShipToAddressID', type: 'int', fk: [6, 'AddressID'] },
      { name: 'ShipMethodID', type: 'int' },
      { name: 'CreditCardID', type: 'int', nullable: true },
      { name: 'CreditCardApprovalCode', type: 'varchar(15)', nullable: true },
      { name: 'CurrencyRateID', type: 'int', nullable: true },
      { name: 'SubTotal', type: 'money', default: '((0.00))', desc: 'Sales subtotal. Computed as SUM(SalesOrderDetail.LineTotal)for the appropriate SalesOrderID.' },
      { name: 'TaxAmt', type: 'money', default: '((0.00))' },
      { name: 'Freight', type: 'money', default: '((0.00))' },
      { name: 'TotalDue', type: 'money', computed: '(isnull(([SubTotal]+[TaxAmt])+[Freight],(0)))', desc: 'Total due from customer. Computed as Subtotal + TaxAmt + Freight.' },
      { name: 'Comment', type: 'nvarchar(128)', nullable: true },
      ...AUDIT,
    ],
    indexes: [
      idx(101, 'PK_SalesOrderHeader_SalesOrderID', ['SalesOrderID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 184_233, scans: 1_204, lookups: 0, updates: 3_112, last_seek: '2026-08-26T08:59:01Z', last_scan: '2026-08-25T22:10:00Z' } }),
      idx(102, 'AK_SalesOrderHeader_rowguid', ['rowguid'], { is_unique: true, is_unique_constraint: true, usage: { seeks: 0, scans: 0, lookups: 0, updates: 3_112 }, is_unused: true }),
      idx(103, 'AK_SalesOrderHeader_SalesOrderNumber', ['SalesOrderNumber'], { is_unique: true, is_unique_constraint: true, usage: { seeks: 1_902, scans: 0, lookups: 0, updates: 3_112 } }),
      idx(104, 'IX_SalesOrderHeader_CustomerID', ['CustomerID'], { usage: { seeks: 52_110, scans: 12, lookups: 0, updates: 3_112, last_seek: '2026-08-26T08:40:11Z' } }),
      idx(105, 'IX_SalesOrderHeader_SalesPersonID', ['SalesPersonID'], { usage: { seeks: 0, scans: 0, lookups: 0, updates: 3_112 }, is_unused: true }),
    ],
    checks: [
      { id: 501, name: 'CK_SalesOrderHeader_Status', definition: '([Status]>=(0) AND [Status]<=(8))', is_disabled: false },
      { id: 502, name: 'CK_SalesOrderHeader_DueDate', definition: '([DueDate]>=[OrderDate])', is_disabled: false },
      { id: 503, name: 'CK_SalesOrderHeader_SubTotal', definition: '([SubTotal]>=(0.00))', is_disabled: false },
    ],
    stats: tableStats(31_465, 6_048, 3_336),
    missing_indexes: [
      { id: 1, equality_columns: '[Status]', inequality_columns: '[OrderDate]', included_columns: '[CustomerID], [TotalDue]', user_seeks: 1_420, user_scans: 0, avg_cost: 12.4, avg_impact: 91.2, improvement_measure: 1_605_491, suggested_ddl: 'CREATE NONCLUSTERED INDEX [IX_SalesOrderHeader_Status_OrderDate] ON [Sales].[SalesOrderHeader] ([Status], [OrderDate]) INCLUDE ([CustomerID], [TotalDue])' },
    ],
    lineage_status: 'n/a',
  },
  {
    id: 2, db: DB, schema: 'Sales', name: 'Customer', kind: 'table', scope: 'in_scope',
    description: 'Current customer information. Also see the Person and Store tables.',
    modified_at: '2024-02-11T10:14:00Z',
    columns: [
      { name: 'CustomerID', type: 'int', identity: true, pk: true, desc: 'Primary key.' },
      { name: 'PersonID', type: 'int', nullable: true, fk: [5, 'BusinessEntityID'], desc: 'Foreign key to Person.BusinessEntityID' },
      { name: 'StoreID', type: 'int', nullable: true, fk: [21, 'BusinessEntityID'] },
      { name: 'TerritoryID', type: 'int', nullable: true, fk: [20, 'TerritoryID'] },
      { name: 'AccountNumber', type: 'varchar(10)', computed: "(isnull('AW'+[dbo].[ufnLeadingZeros]([CustomerID]),''))", desc: 'Unique number identifying the customer assigned by the accounting system.' },
      ...AUDIT,
    ],
    indexes: [
      idx(201, 'PK_Customer_CustomerID', ['CustomerID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 90_211, scans: 402, lookups: 0, updates: 88 } }),
      idx(202, 'AK_Customer_AccountNumber', ['AccountNumber'], { is_unique: true, is_unique_constraint: true, usage: { seeks: 12, scans: 0, lookups: 0, updates: 88 } }),
      idx(203, 'IX_Customer_TerritoryID', ['TerritoryID'], { usage: { seeks: 0, scans: 0, lookups: 0, updates: 88 }, is_unused: true }),
    ],
    stats: tableStats(19_820, 1_048, 1_320),
    lineage_status: 'ok',
  },
  {
    id: 3, db: DB, schema: 'Sales', name: 'SalesOrderDetail', kind: 'table', scope: 'in_scope',
    description: 'Individual products associated with a specific sales order. See also SalesOrderHeader.',
    modified_at: '2024-02-11T10:14:00Z',
    columns: [
      { name: 'SalesOrderID', type: 'int', pk: true, fk: [1, 'SalesOrderID'], desc: 'Primary key. Foreign key to SalesOrderHeader.SalesOrderID.' },
      { name: 'SalesOrderDetailID', type: 'int', identity: true, pk: true, desc: 'Primary key. One incremental unique number per product sold.' },
      { name: 'CarrierTrackingNumber', type: 'nvarchar(25)', nullable: true },
      { name: 'OrderQty', type: 'smallint', desc: 'Quantity ordered per product.' },
      { name: 'ProductID', type: 'int', fk: [11, 'ProductID'], desc: 'Product sold to customer. Foreign key to Product.ProductID.' },
      { name: 'SpecialOfferID', type: 'int' },
      { name: 'UnitPrice', type: 'money', desc: 'Selling price of a single product.' },
      { name: 'UnitPriceDiscount', type: 'money', default: '((0.0))' },
      { name: 'LineTotal', type: 'numeric(38,6)', computed: '(isnull(([UnitPrice]*((1.0)-[UnitPriceDiscount]))*[OrderQty],(0.0)))', desc: 'Per product subtotal. Computed as UnitPrice * (1 - UnitPriceDiscount) * OrderQty.' },
      ...AUDIT,
    ],
    indexes: [
      idx(301, 'PK_SalesOrderDetail_SalesOrderID_SalesOrderDetailID', ['SalesOrderID', 'SalesOrderDetailID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 402_112, scans: 3_310, lookups: 0, updates: 9_004 } }),
      idx(302, 'IX_SalesOrderDetail_ProductID', ['ProductID'], { usage: { seeks: 77_120, scans: 0, lookups: 0, updates: 9_004 } }),
      idx(303, 'AK_SalesOrderDetail_rowguid', ['rowguid'], { is_unique: true, is_unique_constraint: true, usage: { seeks: 0, scans: 0, lookups: 0, updates: 9_004 }, is_unused: true }),
    ],
    checks: [
      { id: 511, name: 'CK_SalesOrderDetail_OrderQty', definition: '([OrderQty]>(0))', is_disabled: false },
      { id: 512, name: 'CK_SalesOrderDetail_UnitPrice', definition: '([UnitPrice]>=(0.00))', is_disabled: false },
    ],
    stats: tableStats(121_317, 10_264, 7_112),
    lineage_status: 'n/a',
  },
  {
    id: 4, db: DB, schema: 'Sales', name: 'vIndividualCustomer', kind: 'view', scope: 'in_scope',
    description: 'Individual customers (names and addresses) that purchase Adventure Works Cycles products online.',
    modified_at: '2024-02-11T10:14:00Z',
    columns: [
      { name: 'BusinessEntityID', type: 'int' },
      { name: 'Title', type: 'nvarchar(8)', nullable: true },
      { name: 'FirstName', type: 'nvarchar(50)' },
      { name: 'MiddleName', type: 'nvarchar(50)', nullable: true },
      { name: 'LastName', type: 'nvarchar(50)' },
      { name: 'Suffix', type: 'nvarchar(10)', nullable: true },
      { name: 'PhoneNumber', type: 'nvarchar(25)', nullable: true },
      { name: 'PhoneNumberType', type: 'nvarchar(50)', nullable: true },
      { name: 'EmailAddress', type: 'nvarchar(50)', nullable: true },
      { name: 'EmailPromotion', type: 'int' },
      { name: 'AddressType', type: 'nvarchar(50)' },
      { name: 'AddressLine1', type: 'nvarchar(60)' },
      { name: 'AddressLine2', type: 'nvarchar(60)', nullable: true },
      { name: 'City', type: 'nvarchar(30)' },
      { name: 'StateProvinceName', type: 'nvarchar(50)' },
      { name: 'PostalCode', type: 'nvarchar(15)' },
      { name: 'CountryRegionName', type: 'nvarchar(50)' },
      { name: 'Demographics', type: 'xml', nullable: true },
    ],
    definition: `CREATE VIEW [Sales].[vIndividualCustomer]
AS
SELECT
    p.[BusinessEntityID]
    ,p.[Title]
    ,p.[FirstName]
    ,p.[MiddleName]
    ,p.[LastName]
    ,p.[Suffix]
    ,pp.[PhoneNumber]
    ,pnt.[Name] AS [PhoneNumberType]
    ,ea.[EmailAddress]
    ,p.[EmailPromotion]
    ,at.[Name] AS [AddressType]
    ,a.[AddressLine1]
    ,a.[AddressLine2]
    ,a.[City]
    ,[StateProvinceName] = sp.[Name]
    ,a.[PostalCode]
    ,[CountryRegionName] = cr.[Name]
    ,p.[Demographics]
FROM [Person].[Person] p
    INNER JOIN [Person].[BusinessEntityAddress] bea
    ON bea.[BusinessEntityID] = p.[BusinessEntityID]
    INNER JOIN [Person].[Address] a
    ON a.[AddressID] = bea.[AddressID]
    INNER JOIN [Person].[StateProvince] sp
    ON sp.[StateProvinceID] = a.[StateProvinceID]
    INNER JOIN [Person].[CountryRegion] cr
    ON cr.[CountryRegionCode] = sp.[CountryRegionCode]
    INNER JOIN [Person].[AddressType] at
    ON at.[AddressTypeID] = bea.[AddressTypeID]
    INNER JOIN [Sales].[Customer] c
    ON c.[PersonID] = p.[BusinessEntityID]
    LEFT OUTER JOIN [Person].[EmailAddress] ea
    ON ea.[BusinessEntityID] = p.[BusinessEntityID]
    LEFT OUTER JOIN [Person].[PersonPhone] pp
    ON pp.[BusinessEntityID] = p.[BusinessEntityID]
    LEFT OUTER JOIN [Person].[PhoneNumberType] pnt
    ON pnt.[PhoneNumberTypeID] = pp.[PhoneNumberTypeID]
WHERE c.StoreID IS NULL;`,
    stats: null,
    lineage_status: 'ok',
  },
  {
    id: 5, db: DB, schema: 'Person', name: 'Person', kind: 'table', scope: 'cascaded',
    description: 'Human beings involved with AdventureWorks: employees, customer contacts, and vendor contacts.',
    modified_at: '2024-02-11T10:14:00Z',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true },
      { name: 'PersonType', type: 'nchar(2)' },
      { name: 'NameStyle', type: 'bit', default: '((0))' },
      { name: 'Title', type: 'nvarchar(8)', nullable: true },
      { name: 'FirstName', type: 'nvarchar(50)', desc: 'First name of the person.' },
      { name: 'MiddleName', type: 'nvarchar(50)', nullable: true },
      { name: 'LastName', type: 'nvarchar(50)', desc: 'Last name of the person.' },
      { name: 'Suffix', type: 'nvarchar(10)', nullable: true },
      { name: 'EmailPromotion', type: 'int', default: '((0))' },
      { name: 'AdditionalContactInfo', type: 'xml', nullable: true },
      { name: 'Demographics', type: 'xml', nullable: true },
      ...AUDIT,
    ],
    indexes: [
      idx(501, 'PK_Person_BusinessEntityID', ['BusinessEntityID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 220_110, scans: 812, lookups: 0, updates: 41 } }),
      idx(502, 'IX_Person_LastName_FirstName_MiddleName', ['LastName', 'FirstName', 'MiddleName'], { usage: { seeks: 8_110, scans: 4, lookups: 0, updates: 41 } }),
    ],
    stats: tableStats(19_972, 30_072, 8_544, { compression: 'PAGE' }),
    lineage_status: 'n/a',
  },
  {
    id: 6, db: DB, schema: 'Person', name: 'Address', kind: 'table', scope: 'cascaded',
    description: 'Street address information for customers, employees, and vendors.',
    columns: [
      { name: 'AddressID', type: 'int', identity: true, pk: true },
      { name: 'AddressLine1', type: 'nvarchar(60)', desc: 'First street address line.' },
      { name: 'AddressLine2', type: 'nvarchar(60)', nullable: true },
      { name: 'City', type: 'nvarchar(30)' },
      { name: 'StateProvinceID', type: 'int', fk: [25, 'StateProvinceID'] },
      { name: 'PostalCode', type: 'nvarchar(15)' },
      { name: 'SpatialLocation', type: 'geography', nullable: true },
      ...AUDIT,
    ],
    indexes: [idx(601, 'PK_Address_AddressID', ['AddressID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 61_002, scans: 91, lookups: 0, updates: 12 } })],
    stats: tableStats(19_614, 2_408, 4_096),
    lineage_status: 'n/a',
  },
  {
    id: 7, db: DB, schema: 'Person', name: 'EmailAddress', kind: 'table', scope: 'cascaded',
    description: 'Where to send a person email.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true, fk: [5, 'BusinessEntityID'] },
      { name: 'EmailAddressID', type: 'int', identity: true, pk: true },
      { name: 'EmailAddress', type: 'nvarchar(50)', nullable: true },
      ...AUDIT,
    ],
    stats: tableStats(19_972, 1_496, 1_296),
    lineage_status: 'n/a',
  },
  {
    id: 8, db: DB, schema: 'Sales', name: 'iduSalesOrderDetail', kind: 'trigger', scope: 'in_scope',
    description: 'AFTER INSERT, DELETE, UPDATE trigger that inserts a row in the TransactionHistory table, updates ModifiedDate in SalesOrderDetail and updates the SalesOrderHeader.SubTotal column.',
    parent_id: 3,
    trigger: { events: ['INSERT', 'DELETE', 'UPDATE'], is_instead_of: false, is_disabled: false },
    columns: [],
    definition: `CREATE TRIGGER [Sales].[iduSalesOrderDetail] ON [Sales].[SalesOrderDetail]
AFTER INSERT, DELETE, UPDATE AS
BEGIN
    DECLARE @Count int;

    SET @Count = @@ROWCOUNT;
    IF @Count = 0
        RETURN;

    SET NOCOUNT ON;

    BEGIN TRY
        -- If inserting, update SalesOrderHeader.SubTotal
        IF EXISTS (SELECT * FROM inserted)
        BEGIN
            UPDATE [Sales].[SalesOrderHeader]
            SET [Sales].[SalesOrderHeader].[SubTotal] =
                (SELECT SUM([Sales].[SalesOrderDetail].[LineTotal])
                    FROM [Sales].[SalesOrderDetail]
                    WHERE [Sales].[SalesOrderHeader].[SalesOrderID] = [Sales].[SalesOrderDetail].[SalesOrderID])
            WHERE [Sales].[SalesOrderHeader].[SalesOrderID] IN (SELECT inserted.[SalesOrderID] FROM inserted);

            INSERT INTO [Production].[TransactionHistory]
                ([ProductID]
                ,[ReferenceOrderID]
                ,[ReferenceOrderLineID]
                ,[TransactionType]
                ,[TransactionDate]
                ,[Quantity]
                ,[ActualCost])
            SELECT
                inserted.[ProductID]
                ,inserted.[SalesOrderID]
                ,inserted.[SalesOrderDetailID]
                ,'S'
                ,GETDATE()
                ,inserted.[OrderQty]
                ,inserted.[UnitPrice]
            FROM inserted
                INNER JOIN [Sales].[SalesOrderHeader]
                ON inserted.[SalesOrderID] = [Sales].[SalesOrderHeader].[SalesOrderID];
        END;
    END TRY
    BEGIN CATCH
        EXECUTE [dbo].[uspPrintError];

        -- Rollback any active or uncommittable transactions before
        -- inserting information in the ErrorLog
        IF @@TRANCOUNT > 0
        BEGIN
            ROLLBACK TRANSACTION;
        END

        EXECUTE [dbo].[uspLogError];
    END CATCH;
END;`,
    stats: execStats(9_004, 0.9),
    lineage_status: 'ok',
  },
  {
    id: 9, db: DB, schema: 'Production', name: 'TransactionHistory', kind: 'table', scope: 'cascaded',
    description: 'Record of each purchase order, sales order, or work order transaction year to date.',
    columns: [
      { name: 'TransactionID', type: 'int', identity: true, pk: true },
      { name: 'ProductID', type: 'int', fk: [11, 'ProductID'] },
      { name: 'ReferenceOrderID', type: 'int' },
      { name: 'ReferenceOrderLineID', type: 'int', default: '((0))' },
      { name: 'TransactionDate', type: 'datetime', default: '(getdate())' },
      { name: 'TransactionType', type: 'nchar(1)' },
      { name: 'Quantity', type: 'int' },
      { name: 'ActualCost', type: 'money' },
      { name: 'ModifiedDate', type: 'datetime', default: '(getdate())' },
    ],
    indexes: [
      idx(901, 'PK_TransactionHistory_TransactionID', ['TransactionID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 1_204, scans: 40, lookups: 0, updates: 9_004 } }),
      idx(902, 'IX_TransactionHistory_ProductID', ['ProductID'], { usage: { seeks: 0, scans: 0, lookups: 0, updates: 9_004 }, is_unused: true }),
      idx(903, 'IX_TransactionHistory_ReferenceOrderID_ReferenceOrderLineID', ['ReferenceOrderID', 'ReferenceOrderLineID'], { usage: { seeks: 3, scans: 0, lookups: 0, updates: 9_004 } }),
    ],
    stats: tableStats(113_443, 6_288, 4_480),
    lineage_status: 'n/a',
  },
  {
    id: 10, db: DB, schema: 'dbo', name: 'uspGetBillOfMaterials', kind: 'procedure', scope: 'in_scope',
    description: 'Stored procedure using a recursive query to return a multi-level bill of material for the specified ProductID.',
    modified_at: '2024-02-11T10:14:00Z',
    params: [
      { id: 1, parameter_id: 1, name: '@StartProductID', type_display: 'int', is_output: false, has_default_value: false, is_return_value: false, description: 'Input parameter for the stored procedure uspGetBillOfMaterials. Specifies the ProductID.' },
      { id: 2, parameter_id: 2, name: '@CheckDate', type_display: 'datetime', is_output: false, has_default_value: false, is_return_value: false, description: 'Input parameter for the stored procedure uspGetBillOfMaterials. Specifies the date.' },
    ],
    columns: [
      { name: 'ProductAssemblyID', type: 'int' },
      { name: 'ComponentID', type: 'int' },
      { name: 'ComponentDesc', type: 'nvarchar(50)' },
      { name: 'TotalQuantity', type: 'decimal(8,2)' },
      { name: 'StandardPrice', type: 'money' },
      { name: 'ListPrice', type: 'money' },
      { name: 'BOMLevel', type: 'smallint' },
      { name: 'RecursionLevel', type: 'int' },
    ],
    definition: `CREATE PROCEDURE [dbo].[uspGetBillOfMaterials]
    @StartProductID [int],
    @CheckDate [datetime]
AS
BEGIN
    SET NOCOUNT ON;

    -- Use recursive query to generate a multi-level Bill of Material (i.e. all level 1
    -- components of a level 0 assembly, all level 2 components of a level 1 assembly)
    -- The CheckDate eliminates any components that are no longer used in the product on this date.
    WITH [BOM_cte]([ProductAssemblyID], [ComponentID], [ComponentDesc], [PerAssemblyQty], [StandardCost], [ListPrice], [BOMLevel], [RecursionLevel]) -- CTE name and columns
    AS (
        SELECT b.[ProductAssemblyID], b.[ComponentID], p.[Name], b.[PerAssemblyQty], p.[StandardCost], p.[ListPrice], b.[BOMLevel], 0 -- Get the initial list of components for the bike assembly
        FROM [Production].[BillOfMaterials] b
            INNER JOIN [Production].[Product] p
            ON b.[ComponentID] = p.[ProductID]
        WHERE b.[ProductAssemblyID] = @StartProductID
            AND @CheckDate >= b.[StartDate]
            AND @CheckDate <= ISNULL(b.[EndDate], @CheckDate)
        UNION ALL
        SELECT b.[ProductAssemblyID], b.[ComponentID], p.[Name], b.[PerAssemblyQty], p.[StandardCost], p.[ListPrice], b.[BOMLevel], [RecursionLevel] + 1 -- Join recursive component list to the CTE
        FROM [BOM_cte] cte
            INNER JOIN [Production].[BillOfMaterials] b
            ON b.[ProductAssemblyID] = cte.[ComponentID]
            INNER JOIN [Production].[Product] p
            ON b.[ComponentID] = p.[ProductID]
        WHERE @CheckDate >= b.[StartDate]
            AND @CheckDate <= ISNULL(b.[EndDate], @CheckDate)
        )
    -- Outer select from the CTE
    SELECT b.[ProductAssemblyID], b.[ComponentID], b.[ComponentDesc], SUM(b.[PerAssemblyQty]) AS [TotalQuantity] , b.[StandardCost], b.[ListPrice], b.[BOMLevel], b.[RecursionLevel]
    FROM [BOM_cte] b
    GROUP BY b.[ComponentID], b.[ComponentDesc], b.[ProductAssemblyID], b.[BOMLevel], b.[RecursionLevel], b.[StandardCost], b.[ListPrice]
    ORDER BY b.[BOMLevel], b.[ProductAssemblyID], b.[ComponentID]
    OPTION (MAXRECURSION 25)
END;`,
    stats: execStats(4_312, 18.4),
    lineage_status: 'partial',
    lineage_issues: [
      { kind: 'unsupported', statement_index: 1, message: 'Recursive CTE: component columns resolved through the anchor member only.', snippet: 'WITH [BOM_cte](...) AS (SELECT ... UNION ALL SELECT ...' },
    ],
  },
  {
    id: 11, db: DB, schema: 'Production', name: 'Product', kind: 'table', scope: 'cascaded',
    description: 'Products sold or used in the manfacturing of sold products.',
    columns: [
      { name: 'ProductID', type: 'int', identity: true, pk: true },
      { name: 'Name', type: 'nvarchar(50)' },
      { name: 'ProductNumber', type: 'nvarchar(25)' },
      { name: 'MakeFlag', type: 'bit', default: '((1))' },
      { name: 'FinishedGoodsFlag', type: 'bit', default: '((1))' },
      { name: 'Color', type: 'nvarchar(15)', nullable: true },
      { name: 'SafetyStockLevel', type: 'smallint' },
      { name: 'ReorderPoint', type: 'smallint' },
      { name: 'StandardCost', type: 'money' },
      { name: 'ListPrice', type: 'money' },
      { name: 'Size', type: 'nvarchar(5)', nullable: true },
      { name: 'Weight', type: 'decimal(8,2)', nullable: true },
      { name: 'ProductSubcategoryID', type: 'int', nullable: true },
      { name: 'ProductModelID', type: 'int', nullable: true },
      { name: 'SellStartDate', type: 'datetime' },
      { name: 'SellEndDate', type: 'datetime', nullable: true },
      { name: 'DiscontinuedDate', type: 'datetime', nullable: true },
      ...AUDIT,
    ],
    indexes: [idx(1101, 'PK_Product_ProductID', ['ProductID'], { type_desc: 'CLUSTERED', is_unique: true, is_primary_key: true, usage: { seeks: 310_020, scans: 1_502, lookups: 0, updates: 3 } })],
    stats: tableStats(504, 80, 128),
    lineage_status: 'n/a',
  },
  {
    id: 12, db: DB, schema: 'dbo', name: 'SalesTargets', kind: 'external', scope: 'external',
    external: { server: 'REPORTING01', database: 'FinanceDW' },
    columns: [],
    lineage_status: 'n/a',
  },
  {
    id: 13, db: DB, schema: 'Sales', name: 'vSalesQuota', kind: 'view', scope: 'in_scope',
    description: 'Sales quota per salesperson joined with the finance targets held on the reporting linked server.',
    modified_at: '2025-11-03T16:02:00Z',
    columns: [
      { name: 'BusinessEntityID', type: 'int' },
      { name: 'SalesQuota', type: 'money', nullable: true },
      { name: 'Target', type: 'money', nullable: true },
      { name: 'Bonus', type: 'money' },
    ],
    definition: `CREATE VIEW [Sales].[vSalesQuota]
AS
SELECT sp.[BusinessEntityID]
     , sp.[SalesQuota]
     , t.[Target]
     , sp.[Bonus]
FROM [Sales].[SalesPerson] sp
LEFT JOIN [REPORTING01].[FinanceDW].[dbo].[SalesTargets] t
       ON t.[SalesPersonID] = sp.[BusinessEntityID];`,
    stats: null,
    lineage_status: 'partial',
    lineage_issues: [
      { kind: 'unsupported', statement_index: 0, message: 'Column list of linked-server object [REPORTING01].[FinanceDW].[dbo].[SalesTargets] is unknown; Target is unresolved.', snippet: 'LEFT JOIN [REPORTING01].[FinanceDW].[dbo].[SalesTargets] t' },
    ],
  },
  {
    id: 14, db: DB, schema: 'Sales', name: 'SalesPerson', kind: 'table', scope: 'in_scope',
    description: 'Sales representative current information.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true, fk: [28, 'BusinessEntityID'] },
      { name: 'TerritoryID', type: 'int', nullable: true, fk: [20, 'TerritoryID'] },
      { name: 'SalesQuota', type: 'money', nullable: true },
      { name: 'Bonus', type: 'money', default: '((0.00))' },
      { name: 'CommissionPct', type: 'smallmoney', default: '((0.00))' },
      { name: 'SalesYTD', type: 'money', default: '((0.00))' },
      { name: 'SalesLastYear', type: 'money', default: '((0.00))' },
      ...AUDIT,
    ],
    stats: tableStats(17, 8, 32),
    lineage_status: 'n/a',
  },
  {
    id: 15, db: DB, schema: 'Production', name: 'BillOfMaterials', kind: 'table', scope: 'cascaded',
    description: 'Items required to make bicycles and bicycle subassemblies.',
    columns: [
      { name: 'BillOfMaterialsID', type: 'int', identity: true, pk: true },
      { name: 'ProductAssemblyID', type: 'int', nullable: true, fk: [11, 'ProductID'] },
      { name: 'ComponentID', type: 'int', fk: [11, 'ProductID'] },
      { name: 'StartDate', type: 'datetime', default: '(getdate())' },
      { name: 'EndDate', type: 'datetime', nullable: true },
      { name: 'UnitMeasureCode', type: 'nchar(3)' },
      { name: 'BOMLevel', type: 'smallint' },
      { name: 'PerAssemblyQty', type: 'decimal(8,2)', default: '((1.00))' },
      { name: 'ModifiedDate', type: 'datetime', default: '(getdate())' },
    ],
    stats: tableStats(2_679, 176, 264),
    lineage_status: 'n/a',
  },
  {
    id: 16, db: DB, schema: 'dbo', name: 'ufnLeadingZeros', kind: 'scalar_function', scope: 'in_scope',
    description: 'Scalar function used by the Sales.Customer table to help set the account number.',
    params: [
      { id: 1, parameter_id: 1, name: '@Value', type_display: 'int', is_output: false, has_default_value: false, is_return_value: false },
      { id: 0, parameter_id: 0, name: '', type_display: 'varchar(8)', is_output: false, has_default_value: false, is_return_value: true },
    ],
    columns: [],
    definition: `CREATE FUNCTION [dbo].[ufnLeadingZeros](
    @Value int
)
RETURNS varchar(8)
WITH SCHEMABINDING
AS
BEGIN
    DECLARE @ReturnValue varchar(8);

    SET @ReturnValue = CONVERT(varchar(8), @Value);
    SET @ReturnValue = REPLICATE('0', 8 - DATALENGTH(@ReturnValue)) + @ReturnValue;

    RETURN (@ReturnValue);
END;`,
    stats: execStats(1_202_110, 0.004),
    lineage_status: 'ok',
  },
  {
    id: 17, db: DB, schema: 'dbo', name: 'uspLogError', kind: 'procedure', scope: 'cascaded',
    description: 'Logs error information in the ErrorLog table about the error that caused execution to jump to the CATCH block of a TRY...CATCH construct.',
    params: [{ id: 1, parameter_id: 1, name: '@ErrorLogID', type_display: 'int', is_output: true, has_default_value: true, default_value: '0', is_return_value: false }],
    columns: [],
    definition: `CREATE PROCEDURE [dbo].[uspLogError]
    @ErrorLogID [int] = 0 OUTPUT -- contains the ErrorLogID of the row inserted
AS                               -- by uspLogError in the ErrorLog table
BEGIN
    SET NOCOUNT ON;
    SET @ErrorLogID = 0;
    BEGIN TRY
        IF ERROR_NUMBER() IS NULL
            RETURN;
        IF XACT_STATE() = -1
        BEGIN
            PRINT 'Cannot log error since the current transaction is in an uncommittable state. '
                + 'Rollback the transaction before executing uspLogError in order to successfully log error information.';
            RETURN;
        END
        INSERT [dbo].[ErrorLog]
            ([UserName], [ErrorNumber], [ErrorSeverity], [ErrorState], [ErrorProcedure], [ErrorLine], [ErrorMessage])
        VALUES
            (CONVERT(sysname, CURRENT_USER), ERROR_NUMBER(), ERROR_SEVERITY(), ERROR_STATE(), ERROR_PROCEDURE(), ERROR_LINE(), ERROR_MESSAGE());
        SET @ErrorLogID = @@IDENTITY;
    END TRY
    BEGIN CATCH
        PRINT 'An error occurred in stored procedure uspLogError: ';
        EXECUTE [dbo].[uspPrintError];
        RETURN -1;
    END CATCH
END;`,
    stats: execStats(3, 2.1),
    lineage_status: 'ok',
  },
  {
    id: 18, db: DB, schema: 'dbo', name: 'uspPrintError', kind: 'procedure', scope: 'cascaded',
    description: 'Prints error information about the error that caused execution to jump to the CATCH block of a TRY...CATCH construct.',
    params: [],
    columns: [],
    definition: `CREATE PROCEDURE [dbo].[uspPrintError]
AS
BEGIN
    SET NOCOUNT ON;
    PRINT 'Error ' + CONVERT(varchar(50), ERROR_NUMBER()) +
          ', Severity ' + CONVERT(varchar(5), ERROR_SEVERITY()) +
          ', State ' + CONVERT(varchar(5), ERROR_STATE()) +
          ', Procedure ' + ISNULL(ERROR_PROCEDURE(), '-') +
          ', Line ' + CONVERT(varchar(5), ERROR_LINE());
    PRINT ERROR_MESSAGE();
END;`,
    stats: execStats(3, 0.3),
    lineage_status: 'ok',
  },
  {
    id: 19, db: DB, schema: 'Sales', name: 'vSalesOrderSummary', kind: 'view', scope: 'in_scope',
    description: 'Per-customer, per-year order totals used by the sales dashboard.',
    modified_at: '2026-03-14T09:30:00Z',
    columns: [
      { name: 'CustomerID', type: 'int' },
      { name: 'SalesPersonID', type: 'int', nullable: true },
      { name: 'OrderYear', type: 'int', nullable: true },
      { name: 'OrderCount', type: 'int' },
      { name: 'TotalDue', type: 'money', nullable: true },
    ],
    definition: `CREATE VIEW [Sales].[vSalesOrderSummary]
AS
SELECT h.[CustomerID]
     , h.[SalesPersonID]
     , YEAR(h.[OrderDate])      AS [OrderYear]
     , COUNT_BIG(*)             AS [OrderCount]
     , SUM(h.[TotalDue])        AS [TotalDue]
FROM [Sales].[SalesOrderHeader] h
GROUP BY h.[CustomerID], h.[SalesPersonID], YEAR(h.[OrderDate]);`,
    stats: null,
    lineage_status: 'ok',
  },
  {
    id: 20, db: DB, schema: 'Sales', name: 'SalesTerritory', kind: 'table', scope: 'in_scope',
    description: 'Sales territory lookup table.',
    columns: [
      { name: 'TerritoryID', type: 'int', identity: true, pk: true },
      { name: 'Name', type: 'nvarchar(50)' },
      { name: 'CountryRegionCode', type: 'nvarchar(3)', fk: [26, 'CountryRegionCode'] },
      { name: 'Group', type: 'nvarchar(50)' },
      { name: 'SalesYTD', type: 'money', default: '((0.00))' },
      { name: 'SalesLastYear', type: 'money', default: '((0.00))' },
      { name: 'CostYTD', type: 'money', default: '((0.00))' },
      { name: 'CostLastYear', type: 'money', default: '((0.00))' },
      ...AUDIT,
    ],
    stats: tableStats(10, 8, 48),
    lineage_status: 'n/a',
  },
  {
    id: 21, db: DB, schema: 'Sales', name: 'Store', kind: 'table', scope: 'in_scope',
    description: 'Customers (resellers) of Adventure Works products.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true },
      { name: 'Name', type: 'nvarchar(50)' },
      { name: 'SalesPersonID', type: 'int', nullable: true, fk: [14, 'BusinessEntityID'] },
      { name: 'Demographics', type: 'xml', nullable: true },
      ...AUDIT,
    ],
    stats: tableStats(701, 1_400, 152, { compression: 'ROW' }),
    lineage_status: 'n/a',
  },
  {
    id: 24, db: DB, schema: 'Person', name: 'BusinessEntityAddress', kind: 'table', scope: 'cascaded',
    description: 'Cross-reference table mapping customers, vendors, and employees to their addresses.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true, fk: [5, 'BusinessEntityID'] },
      { name: 'AddressID', type: 'int', pk: true, fk: [6, 'AddressID'] },
      { name: 'AddressTypeID', type: 'int', pk: true },
      ...AUDIT,
    ],
    stats: tableStats(19_614, 1_016, 1_760),
    lineage_status: 'n/a',
  },
  {
    id: 25, db: DB, schema: 'Person', name: 'StateProvince', kind: 'table', scope: 'cascaded',
    description: 'State and province lookup table.',
    columns: [
      { name: 'StateProvinceID', type: 'int', identity: true, pk: true },
      { name: 'StateProvinceCode', type: 'nchar(3)' },
      { name: 'CountryRegionCode', type: 'nvarchar(3)', fk: [26, 'CountryRegionCode'] },
      { name: 'IsOnlyStateProvinceFlag', type: 'bit', default: '((1))' },
      { name: 'Name', type: 'nvarchar(50)' },
      { name: 'TerritoryID', type: 'int', fk: [20, 'TerritoryID'] },
      ...AUDIT,
    ],
    stats: tableStats(181, 16, 64),
    lineage_status: 'n/a',
  },
  {
    id: 26, db: DB, schema: 'Person', name: 'CountryRegion', kind: 'table', scope: 'cascaded',
    description: 'Lookup table containing the ISO standard codes for countries and regions.',
    columns: [
      { name: 'CountryRegionCode', type: 'nvarchar(3)', pk: true },
      { name: 'Name', type: 'nvarchar(50)' },
      { name: 'ModifiedDate', type: 'datetime', default: '(getdate())' },
    ],
    stats: tableStats(238, 16, 32),
    lineage_status: 'n/a',
  },
  {
    id: 27, db: DB, schema: 'Person', name: 'PersonPhone', kind: 'table', scope: 'cascaded',
    description: 'Telephone number and type of a person.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true, fk: [5, 'BusinessEntityID'] },
      { name: 'PhoneNumber', type: 'nvarchar(25)', pk: true },
      { name: 'PhoneNumberTypeID', type: 'int', pk: true },
      { name: 'ModifiedDate', type: 'datetime', default: '(getdate())' },
    ],
    stats: tableStats(19_972, 1_176, 1_056),
    lineage_status: 'n/a',
  },
  {
    id: 28, db: DB, schema: 'HumanResources', name: 'Employee', kind: 'table', scope: 'cascaded',
    description: 'Employee information such as salary, department, and title.',
    columns: [
      { name: 'BusinessEntityID', type: 'int', pk: true, fk: [5, 'BusinessEntityID'] },
      { name: 'NationalIDNumber', type: 'nvarchar(15)' },
      { name: 'LoginID', type: 'nvarchar(256)' },
      { name: 'OrganizationNode', type: 'hierarchyid', nullable: true },
      { name: 'OrganizationLevel', type: 'smallint', nullable: true, computed: '([OrganizationNode].[GetLevel]())' },
      { name: 'JobTitle', type: 'nvarchar(50)' },
      { name: 'BirthDate', type: 'date' },
      { name: 'MaritalStatus', type: 'nchar(1)' },
      { name: 'Gender', type: 'nchar(1)' },
      { name: 'HireDate', type: 'date' },
      { name: 'SalariedFlag', type: 'bit', default: '((1))' },
      { name: 'VacationHours', type: 'smallint', default: '((0))' },
      { name: 'SickLeaveHours', type: 'smallint', default: '((0))' },
      { name: 'CurrentFlag', type: 'bit', default: '((1))' },
      ...AUDIT,
    ],
    stats: tableStats(290, 56, 136),
    lineage_status: 'n/a',
  },
  {
    id: 29, db: DB, schema: 'Sales', name: 'vSalesPerson', kind: 'view', scope: 'in_scope',
    description: 'Sales representative (names and addresses) and their sales-related information.',
    columns: [
      { name: 'BusinessEntityID', type: 'int' },
      { name: 'Title', type: 'nvarchar(8)', nullable: true },
      { name: 'FirstName', type: 'nvarchar(50)' },
      { name: 'LastName', type: 'nvarchar(50)' },
      { name: 'JobTitle', type: 'nvarchar(50)' },
      { name: 'TerritoryName', type: 'nvarchar(50)', nullable: true },
      { name: 'TerritoryGroup', type: 'nvarchar(50)', nullable: true },
      { name: 'SalesQuota', type: 'money', nullable: true },
      { name: 'SalesYTD', type: 'money' },
      { name: 'SalesLastYear', type: 'money' },
    ],
    definition: `CREATE VIEW [Sales].[vSalesPerson]
AS
SELECT
    s.[BusinessEntityID]
    ,p.[Title]
    ,p.[FirstName]
    ,p.[LastName]
    ,e.[JobTitle]
    ,st.[Name] AS [TerritoryName]
    ,st.[Group] AS [TerritoryGroup]
    ,s.[SalesQuota]
    ,s.[SalesYTD]
    ,s.[SalesLastYear]
FROM [Sales].[SalesPerson] s
    INNER JOIN [HumanResources].[Employee] e
    ON e.[BusinessEntityID] = s.[BusinessEntityID]
    INNER JOIN [Person].[Person] p
    ON p.[BusinessEntityID] = s.[BusinessEntityID]
    LEFT OUTER JOIN [Sales].[SalesTerritory] st
    ON st.[TerritoryID] = s.[TerritoryID];`,
    stats: null,
    lineage_status: 'ok',
  },
  {
    id: 30, db: DB, schema: 'dbo', name: 'ufnGetContactInformation', kind: 'table_function', scope: 'in_scope',
    description: 'Table value function returning the first name, last name, job title and contact type for a given contact.',
    params: [{ id: 1, parameter_id: 1, name: '@PersonID', type_display: 'int', is_output: false, has_default_value: false, is_return_value: false }],
    columns: [
      { name: 'PersonID', type: 'int' },
      { name: 'FirstName', type: 'nvarchar(50)', nullable: true },
      { name: 'LastName', type: 'nvarchar(50)', nullable: true },
      { name: 'JobTitle', type: 'nvarchar(50)', nullable: true },
      { name: 'BusinessEntityType', type: 'nvarchar(50)', nullable: true },
    ],
    definition: `CREATE FUNCTION [dbo].[ufnGetContactInformation](@PersonID int)
RETURNS @retContactInformation TABLE
(
    -- Columns returned by the function
    [PersonID] int NOT NULL,
    [FirstName] [nvarchar](50) NULL,
    [LastName] [nvarchar](50) NULL,
    [JobTitle] [nvarchar](50) NULL,
    [BusinessEntityType] [nvarchar](50) NULL
)
AS
-- Returns the first name, last name, job title and business entity type for the specified contact.
-- Since a contact can serve multiple roles, more than one row may be returned.
BEGIN
    IF @PersonID IS NOT NULL
        BEGIN
        IF EXISTS(SELECT * FROM [HumanResources].[Employee] e
                    WHERE e.[BusinessEntityID] = @PersonID)
            INSERT INTO @retContactInformation
                SELECT @PersonID, p.FirstName, p.LastName, e.[JobTitle], 'Employee'
                FROM [HumanResources].[Employee] AS e
                    INNER JOIN [Person].[Person] p
                    ON p.[BusinessEntityID] = e.[BusinessEntityID]
                WHERE e.[BusinessEntityID] = @PersonID;

        IF EXISTS(SELECT * FROM [Sales].[SalesPerson] sp
                    WHERE sp.[BusinessEntityID] = @PersonID)
            INSERT INTO @retContactInformation
                SELECT @PersonID, p.FirstName, p.LastName, NULL, 'Sales Person'
                FROM [Sales].[SalesPerson] AS sp
                    INNER JOIN [Person].[Person] p
                    ON p.[BusinessEntityID] = sp.[BusinessEntityID]
                WHERE sp.[BusinessEntityID] = @PersonID;
        END

    RETURN;
END;`,
    stats: execStats(812, 3.2),
    lineage_status: 'ok',
  },
  {
    id: 31, db: DB, schema: 'dbo', name: 'ProductCatalog', kind: 'synonym', scope: 'in_scope',
    description: 'Synonym for Production.Product used by legacy reports.',
    columns: [],
    stats: null,
    lineage_status: 'n/a',
  },
  {
    id: 32, db: DB, schema: 'Sales', name: 'OrderNumberSeq', kind: 'sequence', scope: 'in_scope',
    columns: [],
    stats: null,
    lineage_status: 'n/a',
  },
]

/** Object-level edges: data flows source → target. */
export const EDGES: FixtureEdge[] = [
  // FKs (child → parent)
  { source: 1, target: 2, kind: 'fk', detail: 'FK_SalesOrderHeader_Customer_CustomerID' },
  { source: 1, target: 6, kind: 'fk', detail: 'FK_SalesOrderHeader_Address_BillToAddressID' },
  { source: 1, target: 14, kind: 'fk', detail: 'FK_SalesOrderHeader_SalesPerson_SalesPersonID' },
  { source: 1, target: 20, kind: 'fk', detail: 'FK_SalesOrderHeader_SalesTerritory_TerritoryID' },
  { source: 3, target: 1, kind: 'fk', detail: 'FK_SalesOrderDetail_SalesOrderHeader_SalesOrderID' },
  { source: 3, target: 11, kind: 'fk', detail: 'FK_SalesOrderDetail_Product_ProductID' },
  { source: 2, target: 5, kind: 'fk', detail: 'FK_Customer_Person_PersonID' },
  { source: 2, target: 21, kind: 'fk', detail: 'FK_Customer_Store_StoreID' },
  { source: 2, target: 20, kind: 'fk', detail: 'FK_Customer_SalesTerritory_TerritoryID' },
  { source: 6, target: 25, kind: 'fk', detail: 'FK_Address_StateProvince_StateProvinceID' },
  { source: 25, target: 26, kind: 'fk', detail: 'FK_StateProvince_CountryRegion_CountryRegionCode' },
  { source: 25, target: 20, kind: 'fk', detail: 'FK_StateProvince_SalesTerritory_TerritoryID' },
  { source: 7, target: 5, kind: 'fk', detail: 'FK_EmailAddress_Person_BusinessEntityID' },
  { source: 27, target: 5, kind: 'fk', detail: 'FK_PersonPhone_Person_BusinessEntityID' },
  { source: 24, target: 5, kind: 'fk', detail: 'FK_BusinessEntityAddress_Person_BusinessEntityID' },
  { source: 24, target: 6, kind: 'fk', detail: 'FK_BusinessEntityAddress_Address_AddressID' },
  { source: 14, target: 28, kind: 'fk', detail: 'FK_SalesPerson_Employee_BusinessEntityID' },
  { source: 14, target: 20, kind: 'fk', detail: 'FK_SalesPerson_SalesTerritory_TerritoryID' },
  { source: 28, target: 5, kind: 'fk', detail: 'FK_Employee_Person_BusinessEntityID' },
  { source: 21, target: 14, kind: 'fk', detail: 'FK_Store_SalesPerson_SalesPersonID' },
  { source: 9, target: 11, kind: 'fk', detail: 'FK_TransactionHistory_Product_ProductID' },
  { source: 15, target: 11, kind: 'fk', detail: 'FK_BillOfMaterials_Product_ComponentID' },
  { source: 20, target: 26, kind: 'fk', detail: 'FK_SalesTerritory_CountryRegion_CountryRegionCode' },
  // Views read from tables (catalog dependencies)
  { source: 5, target: 4, kind: 'catalog' },
  { source: 24, target: 4, kind: 'catalog' },
  { source: 6, target: 4, kind: 'catalog' },
  { source: 25, target: 4, kind: 'catalog' },
  { source: 26, target: 4, kind: 'catalog' },
  { source: 2, target: 4, kind: 'catalog' },
  { source: 7, target: 4, kind: 'catalog' },
  { source: 27, target: 4, kind: 'catalog' },
  { source: 14, target: 13, kind: 'catalog' },
  { source: 12, target: 13, kind: 'catalog', resolution: 'external' },
  { source: 1, target: 19, kind: 'catalog' },
  { source: 14, target: 29, kind: 'catalog' },
  { source: 28, target: 29, kind: 'catalog' },
  { source: 5, target: 29, kind: 'catalog' },
  { source: 20, target: 29, kind: 'catalog' },
  // Procs / functions
  { source: 15, target: 10, kind: 'catalog' },
  { source: 11, target: 10, kind: 'catalog' },
  { source: 16, target: 2, kind: 'catalog', detail: 'computed column AccountNumber' },
  { source: 28, target: 30, kind: 'catalog' },
  { source: 5, target: 30, kind: 'catalog' },
  { source: 14, target: 30, kind: 'catalog' },
  { source: 18, target: 17, kind: 'parsed_exec' },
  // Trigger
  { source: 3, target: 8, kind: 'trigger' },
  { source: 8, target: 9, kind: 'parsed_write' },
  { source: 8, target: 1, kind: 'parsed_write' },
  { source: 8, target: 18, kind: 'parsed_exec' },
  { source: 8, target: 17, kind: 'parsed_exec' },
  // Synonym
  { source: 11, target: 31, kind: 'synonym' },
]

export const COLUMN_EDGES: FixtureColumnEdge[] = [
  // Person.* → Sales.vIndividualCustomer
  { s: [5, 'BusinessEntityID'], t: [4, 'BusinessEntityID'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'Title'], t: [4, 'Title'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'FirstName'], t: [4, 'FirstName'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'MiddleName'], t: [4, 'MiddleName'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'LastName'], t: [4, 'LastName'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'Suffix'], t: [4, 'Suffix'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'EmailPromotion'], t: [4, 'EmailPromotion'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'Demographics'], t: [4, 'Demographics'], confidence: 'exact', transform: 'passthrough' },
  { s: [27, 'PhoneNumber'], t: [4, 'PhoneNumber'], confidence: 'exact', transform: 'passthrough' },
  { s: [7, 'EmailAddress'], t: [4, 'EmailAddress'], confidence: 'exact', transform: 'passthrough' },
  { s: [6, 'AddressLine1'], t: [4, 'AddressLine1'], confidence: 'exact', transform: 'passthrough' },
  { s: [6, 'AddressLine2'], t: [4, 'AddressLine2'], confidence: 'exact', transform: 'passthrough' },
  { s: [6, 'City'], t: [4, 'City'], confidence: 'exact', transform: 'passthrough' },
  { s: [6, 'PostalCode'], t: [4, 'PostalCode'], confidence: 'exact', transform: 'passthrough' },
  { s: [25, 'Name'], t: [4, 'StateProvinceName'], confidence: 'exact', transform: 'passthrough' },
  { s: [26, 'Name'], t: [4, 'CountryRegionName'], confidence: 'exact', transform: 'passthrough' },
  // Sales.SalesOrderHeader → Sales.vSalesOrderSummary
  { s: [1, 'CustomerID'], t: [19, 'CustomerID'], confidence: 'exact', transform: 'passthrough' },
  { s: [1, 'SalesPersonID'], t: [19, 'SalesPersonID'], confidence: 'exact', transform: 'passthrough' },
  { s: [1, 'OrderDate'], t: [19, 'OrderYear'], confidence: 'inferred', transform: 'expression', expression: 'YEAR(h.[OrderDate])' },
  { s: [1, 'TotalDue'], t: [19, 'TotalDue'], confidence: 'inferred', transform: 'aggregate', expression: 'SUM(h.[TotalDue])' },
  // Computed columns (intra-table)
  { s: [1, 'SubTotal'], t: [1, 'TotalDue'], confidence: 'inferred', transform: 'computed', expression: '([SubTotal]+[TaxAmt])+[Freight]' },
  { s: [1, 'TaxAmt'], t: [1, 'TotalDue'], confidence: 'inferred', transform: 'computed', expression: '([SubTotal]+[TaxAmt])+[Freight]' },
  { s: [1, 'Freight'], t: [1, 'TotalDue'], confidence: 'inferred', transform: 'computed', expression: '([SubTotal]+[TaxAmt])+[Freight]' },
  { s: [1, 'SalesOrderID'], t: [1, 'SalesOrderNumber'], confidence: 'inferred', transform: 'computed', expression: "N'SO'+CONVERT([nvarchar](23),[SalesOrderID])" },
  { s: [2, 'CustomerID'], t: [2, 'AccountNumber'], confidence: 'inferred', transform: 'computed', via: 16, expression: "'AW'+[dbo].[ufnLeadingZeros]([CustomerID])" },
  { s: [3, 'UnitPrice'], t: [3, 'LineTotal'], confidence: 'inferred', transform: 'computed', expression: '[UnitPrice]*((1.0)-[UnitPriceDiscount])*[OrderQty]' },
  { s: [3, 'UnitPriceDiscount'], t: [3, 'LineTotal'], confidence: 'inferred', transform: 'computed', expression: '[UnitPrice]*((1.0)-[UnitPriceDiscount])*[OrderQty]' },
  { s: [3, 'OrderQty'], t: [3, 'LineTotal'], confidence: 'inferred', transform: 'computed', expression: '[UnitPrice]*((1.0)-[UnitPriceDiscount])*[OrderQty]' },
  // Trigger writes (via Sales.iduSalesOrderDetail)
  { s: [3, 'ProductID'], t: [9, 'ProductID'], confidence: 'exact', transform: 'passthrough', via: 8 },
  { s: [3, 'SalesOrderID'], t: [9, 'ReferenceOrderID'], confidence: 'exact', transform: 'passthrough', via: 8 },
  { s: [3, 'SalesOrderDetailID'], t: [9, 'ReferenceOrderLineID'], confidence: 'exact', transform: 'passthrough', via: 8 },
  { s: [3, 'OrderQty'], t: [9, 'Quantity'], confidence: 'exact', transform: 'passthrough', via: 8 },
  { s: [3, 'UnitPrice'], t: [9, 'ActualCost'], confidence: 'exact', transform: 'passthrough', via: 8 },
  { s: [3, 'LineTotal'], t: [1, 'SubTotal'], confidence: 'inferred', transform: 'aggregate', via: 8, expression: 'SUM([Sales].[SalesOrderDetail].[LineTotal])' },
  // Sales.vSalesQuota (external → unresolved)
  { s: [14, 'BusinessEntityID'], t: [13, 'BusinessEntityID'], confidence: 'exact', transform: 'passthrough' },
  { s: [14, 'SalesQuota'], t: [13, 'SalesQuota'], confidence: 'exact', transform: 'passthrough' },
  { s: [14, 'Bonus'], t: [13, 'Bonus'], confidence: 'exact', transform: 'passthrough' },
  { s: [12, 'Target'], t: [13, 'Target'], confidence: 'unresolved', transform: 'passthrough', expression: 't.[Target]' },
  // Sales.vSalesPerson
  { s: [14, 'BusinessEntityID'], t: [29, 'BusinessEntityID'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'Title'], t: [29, 'Title'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'FirstName'], t: [29, 'FirstName'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'LastName'], t: [29, 'LastName'], confidence: 'exact', transform: 'passthrough' },
  { s: [28, 'JobTitle'], t: [29, 'JobTitle'], confidence: 'exact', transform: 'passthrough' },
  { s: [20, 'Name'], t: [29, 'TerritoryName'], confidence: 'exact', transform: 'passthrough' },
  { s: [20, 'Group'], t: [29, 'TerritoryGroup'], confidence: 'exact', transform: 'passthrough' },
  { s: [14, 'SalesQuota'], t: [29, 'SalesQuota'], confidence: 'exact', transform: 'passthrough' },
  { s: [14, 'SalesYTD'], t: [29, 'SalesYTD'], confidence: 'exact', transform: 'passthrough' },
  { s: [14, 'SalesLastYear'], t: [29, 'SalesLastYear'], confidence: 'exact', transform: 'passthrough' },
  // dbo.ufnGetContactInformation (multi-statement TVF)
  { s: [5, 'FirstName'], t: [30, 'FirstName'], confidence: 'exact', transform: 'passthrough' },
  { s: [5, 'LastName'], t: [30, 'LastName'], confidence: 'exact', transform: 'passthrough' },
  { s: [28, 'JobTitle'], t: [30, 'JobTitle'], confidence: 'inferred', transform: 'temp' },
  // dbo.uspGetBillOfMaterials result set
  { s: [15, 'ProductAssemblyID'], t: [10, 'ProductAssemblyID'], confidence: 'inferred', transform: 'expression' },
  { s: [15, 'ComponentID'], t: [10, 'ComponentID'], confidence: 'inferred', transform: 'expression' },
  { s: [11, 'Name'], t: [10, 'ComponentDesc'], confidence: 'inferred', transform: 'expression' },
  { s: [15, 'PerAssemblyQty'], t: [10, 'TotalQuantity'], confidence: 'inferred', transform: 'aggregate', expression: 'SUM(b.[PerAssemblyQty])' },
  { s: [11, 'StandardCost'], t: [10, 'StandardPrice'], confidence: 'inferred', transform: 'expression' },
  { s: [11, 'ListPrice'], t: [10, 'ListPrice'], confidence: 'inferred', transform: 'expression' },
  { s: [15, 'BOMLevel'], t: [10, 'BOMLevel'], confidence: 'inferred', transform: 'expression' },
]

// ---------------------------------------------------------------------------
// Scans
// ---------------------------------------------------------------------------

export const SCAN_OPTIONS = {
  cascade_foreign_keys: true,
  include_triggers_of_cascaded_tables: true,
  collect_stats: true,
  parse_lineage: true,
}

export const SCAN_COUNTS = {
  databases: 1,
  schemas: 5,
  tables: 17,
  views: 4,
  procedures: 3,
  functions: 2,
  triggers: 1,
  synonyms: 1,
  externals: 1,
  cascaded: 11,
  columns: 231,
  edges_object: EDGES.length,
  edges_column: COLUMN_EDGES.length,
  lineage_issues: 2,
  warnings: 2,
}

/** Counts for a scan that produced no snapshot (failed / running / cancelled). */
export const EMPTY_COUNTS = { ...SCAN_COUNTS, tables: 0, views: 0, procedures: 0, functions: 0, triggers: 0, synonyms: 0, externals: 0, cascaded: 0, columns: 0, edges_object: 0, edges_column: 0, lineage_issues: 0, warnings: 0 }

export const INITIAL_SCANS: ScanSummary[] = [
  {
    id: 2,
    connection: CONNECTION,
    status: 'succeeded',
    started_at: '2026-08-26T09:12:31Z',
    finished_at: '2026-08-26T09:12:39Z',
    duration_ms: 8_214,
    options: SCAN_OPTIONS,
    counts: SCAN_COUNTS,
    server_name: 'mssql',
    server_version: '16.0.4165.4',
    server_edition: 'Developer Edition (64-bit)',
    auth_scheme: 'SQL',
    driver: 'pyodbc',
  },
  {
    id: 1,
    connection: CONNECTION,
    status: 'failed',
    started_at: '2026-08-25T17:40:02Z',
    finished_at: '2026-08-25T17:40:03Z',
    duration_ms: 1_102,
    options: SCAN_OPTIONS,
    counts: EMPTY_COUNTS,
    error: "Login failed for user 'sa'. (18456)",
  },
]

export const INITIAL_ANNOTATIONS: Annotation[] = [
  {
    target_kind: 'object',
    target_key: `${CONNECTION}|${DB}|Sales|SalesOrderHeader`,
    description: 'Header row for every order; the source of truth for revenue reporting.',
    notes: 'Row count grows ~2k/month. Partition by OrderDate is on the backlog.',
    tags: ['core', 'pii'],
    updated_at: '2026-08-20T10:00:00Z',
  },
  {
    target_kind: 'object',
    target_key: `${CONNECTION}|${DB}|Sales|vIndividualCustomer`,
    description: null,
    notes: 'Used by the marketing export job nightly.',
    tags: ['reporting'],
    updated_at: '2026-08-21T10:00:00Z',
  },
  {
    target_kind: 'column',
    target_key: `${CONNECTION}|${DB}|Person|Person|FirstName`,
    description: 'Given name; PII.',
    notes: null,
    tags: ['pii'],
    updated_at: '2026-08-21T10:00:00Z',
  },
]

export const TAG_COLORS: Record<string, string> = {
  core: '#4f46e5',
  pii: '#e11d48',
  reporting: '#0d9488',
}
