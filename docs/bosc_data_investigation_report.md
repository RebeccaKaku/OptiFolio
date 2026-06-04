# Bank of Shanghai (BOSC) Wealth Management Data Investigation Report

This report documents the findings from the investigation of the Bank of Shanghai (BOSC) personal banking wealth management section, focusing on locating product characteristics (risk level, establishment/maturity dates, subscription/redemption rules, prospectus PDF links, fee rates, etc.), analyzing network requests, and assessing the feasibility of automated data fetching.

---

## 1. Product Characteristics & Metadata Analysis

Based on the raw product list snapshot file `data/bosc/raw/bosc_all_products_snapshot_20260603.json` (containing 279 unique records), we inspected several target products. The analysis of key fields is as follows:

### Sample Product Details

| Field / Attribute | WH2025109A | J13164 | WPXK24M1203A |
| :--- | :--- | :--- | :--- |
| **Product Name** | 上银理财慧精灵9号 | 苏银理财恒源融达1号6月N | 上银理财鑫享利-12个月周期开放式3号A |
| **Product Code** | `WH2025109A` | `J13164` | `WPXK24M1203A` |
| **Risk Level (风险等级)** | `1` (R1 - Low) | `2` (R2 - Medium-Low) | `2` (R2 - Medium-Low) |
| **Establish Date (成立日)** | `2025-09-11` | `2026-01-14` | `2024-07-17` |
| **Maturity Date (到期日)** | `2095-09-10` (Cash-like long-term) | `2038-09-03` | `2054-06-11` |
| **Product Type Desc** | `开放式` (Open-ended) | `开放式` (Open-ended) | `净值型周期开放式` (Net worth cycle open-ended) |
| **Product Category** | `活钱打理` (Cash management) | *(Empty)* | `稳健精品` (Steady growth boutique) |
| **Shelves Type Desc** | `现金管理` (Cash management) | `稳健增值` (Steady growth) | `稳健增值` (Steady growth) |
| **Period Desc** | *(Empty)* | `182天` (182 days) | *(Empty)* |
| **taCode (登记托管理财子)** | `Y58` (上银理财) | `Y04` (苏银理财) | `Y58` (上银理财) |
| **taShortName** | `上银理财` | `苏银理财` | `上银理财` |
| **pfirstAmt (起购金额)** | `0.01` RMB | `10000.00` RMB | `1.00` RMB |
| **isDocFlag** | `0` | `0` | `0` |
| **Yield / Rate** | `1.85` | `0` | `0` |

### Key Observations:
1. **Risk Level (`riskLevel`)**: Ranges from `1` to `3` in the dataset, representing the bank's internal risk rating (R1 to R3).
2. **Establishment/Maturity Dates (`estabDate`, `incomeEndDate`)**: Present for all products. Cash management products like `WH2025109A` have artificial far-future maturity dates (e.g. 70-year duration to `2095-09-10`).
3. **Open Subscription/Redemption Rules**:
   - Basic cycle length is indicated in `periodDesc` or `cycleDays` (e.g. `182天` for `J13164`).
   - Detailed rules are provided textually in `modelcommentDesc` (describing benchmark targets, asset allocation thresholds, etc.).
4. **Partner Products**: The list includes third-party distributed wealth management products such as those of **苏银理财** (`taCode`: `Y04`), showing that the BOSC platform acts as both a manufacturer (via **上银理财** `Y58`) and a distributor.
5. **Missing Fields**: Detailed fee structures (management, custody, sales service, subscription/redemption fee rates) and prospectus PDF links are **not** present in the public list metadata.

---

## 2. Network (XHR/Fetch) Requests & API Details

The public web portal and bank database utilize two major API endpoints for listing products and querying historical net values.

### A. Discovering Products (Product Metadata List)
* **Endpoint URL**: `POST https://www.bosc.cn/apiQry/apiPCQry/qryPcFinanceProductZh`
* **Request Method**: `POST`
* **Request Headers**:
  ```http
  Content-Type: application/json
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...
  ```
* **Query Parameters / Payload**:
  ```json
  {
    "current": 1,
    "size": 1000
  }
  ```
* **Response Format**: JSON.
  ```json
  {
    "code": 200,
    "success": true,
    "msg": "操作成功",
    "data": {
      "records": [
        {
          "prdCode": "WH2025109A",
          "prdName": "上银理财慧精灵9号",
          "riskLevel": 1,
          "estabDate": "2025-09-11",
          "incomeEndDate": "2095-09-10",
          ...
        }
      ],
      "total": 279,
      "size": 1000,
      "current": 1,
      "pages": 1
    }
  }
  ```

### B. Product Historical Net Value
* **Endpoint URL**: `GET https://www.bosc.cn/apiQry/apiPCQry/v2/qryMCFinanceNetProHisValueForPersonPage`
* **Request Method**: `GET`
* **Query Parameters**:
  * `prdCode`: Product code (e.g. `WPXK24M1203A`).
  * `taCode`: Manager code (e.g. `Y58` or `Y04`).
  * `prodSeries`: Product series (e.g. `W`, or empty).
  * `size`: Records per page (strict maximum of `20` due to bank Web Application Firewall rules).
  * `current`: Page index (1-based).
* **Response Format**: JSON.
  ```json
  {
    "code": 200,
    "success": true,
    "msg": "操作成功",
    "data": {
      "records": [
        {
          "prdCode": "WPXK24M1203A",
          "navDate": "2026/06/03",
          "nav": "1.0254",
          "accNav": "1.0254",
          "sevenDaysYearRate": null
        }
      ],
      "total": 120,
      "size": 20,
      "current": 1,
      "pages": 6
    }
  }
  ```
* **Notes**: Cash management products (like `WH2025109A`) return 0 records because their yield reporting formats (Seven-day Annualized Yield, etc.) do not map to the standard net asset value (NAV) schema used by this endpoint.

---

## 3. Web Portal & Personal Online Banking Redirects

Navigating to the personal banking wealth home page `https://ebanks.bankofshanghai.com/prd/WealthHome/Index` triggers a series of security controls and redirects:

1. **Authentication Wall**: Users are immediately redirected to the pre-login portal:
   `https://ebanks.bankofshanghai.com/pweb/prelogin.do?LoginType=R&_locale=zh_CN`
2. **Security Controls**:
   - The browser loads cryptographic plugins and device fingerprinting libraries:
     * `https://dfg.bosc.cn:9080/public/downloads/frms-fingerprint.js`
     * `https://powerservice.csii.com.cn:50876/SetUKeyVendor` (checks for local U-Key drivers)
     * Local loopbacks (`127.0.0.1:6206` / `6207`) are queried to check if the security keyboard/credential assistant software is installed.
3. **Encrypted Handshake**:
   - Requests such as `POST /pweb/GenerateMcryptKey.do` and `POST /pweb/financeForLoginQry.do` are initiated to establish session-specific public keys and retrieve basic login states.
4. **Feasibility of Detail Scrapes**: Since the web pages displaying full prospectus documents and fee details require logging in, crawling the authenticated online banking pages is highly infeasible for automated backend pipelines.

---

## 4. Prospectus & Fee Rates Retrieval Feasibility

### A. How Prospectus URLs are Structured
* **No Direct Link Mapping**: The public `qryPcFinanceProductZh` API output does not map to prospectus PDF documents. The field `isDocFlag` is `0` for all target products, and there are no download fields.
* **Alternative Retrieval Channels**:
  1. **Distributor Disclosure Channels**: Major distributing partners (e.g. `suyinwealth.com` for Y04, or cooperative banks distributing Y58) often provide public announcements detailing fee rate updates (e.g. sales service fees and investment management fees) which are indexed by Google/Bing.
  2. **ChinaWealth Database (中国理财网)**: Every legally registered bank wealth management product possesses a registration code (registration number beginning with "Z" or "C"). Searching this code on [ChinaWealth](https://www.chinawealth.com.cn) returns the authoritative filing document containing all fee structures and prospectus details.
  3. **PDF Parsing Necessity**: If exact fee rates (management, custody, sales, subscription, and redemption fee percentages) are required, they must be parsed directly from the prospectus PDF files, as the public API endpoints only expose interest/benchmark descriptions (`modelcommentDesc`) rather than individual fee components.

---

## 5. Conclusion & Recommendations

1. **Leverage Public APIs**: The endpoints under `https://www.bosc.cn/apiQry` are fully public and require no authentication. They are robust enough to fetch product metadata lists and historical net asset values.
2. **Handle Special Net Values**: Establish a fallback schema for cash management products that don't return standard NAV page structures.
3. **Automate Prospectus Lookup**: To programmatically obtain PDF files and fee rates without logging in, implement a search parser targeting distributor notice channels or query the official ChinaWealth portal using the products' registration codes.
