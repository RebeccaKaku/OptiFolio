# Industrial and Commercial Bank of China (ICBC) Wealth Management Data Investigation Report

This report outlines the technical findings regarding the structure, location, and accessibility of wealth management product characteristics (risk level, establishment/maturity dates, subscription/redemption rules, prospectus PDF links, fee rates, etc.) on the ICBC personal banking and official portals.

---

## 1. API Metadata Discovery

ICBC employs a hybrid architecture for its wealth management services. The main personal banking portal (`mybank.icbc.com.cn`) uses servlet-based operations returning HTML fragments, while its content-serving subdomains (like `papi.icbc.com.cn`) expose session-less REST JSON endpoints.

### 1.1 Product List (Discovery) API
* **Endpoint URL**: `POST https://mybank.icbc.com.cn/servlet/ICBCBaseReqServletNoSession`
* **Query Parameters (URL)**: `dse_operationName=per_FinanceCurProListP3NSOp`
* **Request Format (Form Data / URL Encoded)**:
  ```http
  nowPageNum_turn: 1
  pageFlag_turn: 1
  Area_code: 0200
  useFinanceSolrFlag: 1
  financeQueryCondition: {"financeSelectType":"1","financeSelectValue":""}
  ```
* **Response Format**: A GBK-encoded HTML fragment containing product card components.
* **Retrieved Metadata (from HTML)**: Product Name, Product Code, Risk Level (PR1-PR5), Yield Benchmark, Product Term/Duration, Minimum Subscription Amount.
* **Missing Metadata**: Establishment date, maturity date, exact fee rates, and prospectus links are missing or incomplete in this listing.

### 1.2 Public Net Value API (Dynamic Characteristics)
To fetch net value history and core product tags publicly without requiring a logged-in user session, the portal calls a JSON API on `papi.icbc.com.cn`.
* **Endpoint URL**: `POST https://papi.icbc.com.cn/finance/deposit/consignment/getNetValueList`
* **Headers**:
  ```http
  Content-Type: application/json
  Origin: https://www.icbc.com.cn
  Referer: https://www.icbc.com.cn/
  ```
* **Request Payload (JSON)**:
  ```json
  {
    "prodId": "23GS8125",
    "pageIndex": 1,
    "pageSize": 10
  }
  ```
* **Response Format (GBK-encoded JSON)**:
  ```json
  {
    "code": 0,
    "message": "成功",
    "data": {
      "pageIndex": 1,
      "pageSize": 10,
      "pages": 22,
      "total": 212,
      "list": [
        {
          "workDate": "2026-06-02",
          "value": "1.150100",
          "totValue": "1.150100",
          "notes": "",
          "prodName": "工银理财·全球添益双周美元产品(封闭2023.4.19-2023.10.24)",
          "prodType": "1",
          "salePrice": "1.150100",
          "buyPrice": "1.150100",
          "field3": "533665409.62",
          "tableType": "1",
          "fRaisingMethod": "1",
          "fOperationMethod": "1",
          "fProductType": "1",
          "fSubscribePrice": "1.000000"
        }
      ]
    }
  }
  ```
* **Key Fields Discovered**:
  * `prodName`: Explicitly includes the product's establishment date and initial closed-period maturity (e.g. `封闭2023.4.19-2023.10.24` indicates a release date of **2023-04-19** and closed phase ending **2023-10-24**).
  * `value` / `totValue`: Net asset value (NAV) and accumulated NAV.
  * `field3`: Product asset/scale size (e.g., `533665409.62` USD).
  * `fRaisingMethod`: Raising method (`1` = Public / 公募).
  * `fOperationMethod`: Operation method (`1` = Open-ended / 开放式).
  * `fProductType`: Asset subclass (`1` = Fixed Income / 固定收益类).

---

## 2. Product Detail and Purchase Flow Integration

Unlike other banks that host public static detail pages, ICBC gates its transactional detail and purchase interfaces inside its e-banking framework.

* **Buy/Detail Action**: In the list view, Clicking a product name or buy button triggers a JavaScript call:
  `javascript:buySubmit('26G2066A','0','','','1');`
* **Internal Routing**: This script redirects inside an authenticated iframe, invoking internal services like `AtomSerivceSubmit('PBL200403', ...)` or `AtomSerivceSubmit('PBL20211121', ...)`.
* **Implication**: There are no public, search-engine-indexable web pages on `mybank.icbc.com.cn` showing detailed fee schedules or rules.

---

## 3. HTML Selector Paths (List Discovery)

If parsing the session-less HTML discovery list is required, use these selector paths:

* **Product Container Card**: `div.ebdp-pc4promote-circularcontainer`
* **Product Name**: `span.ebdp-pc4promote-circularcontainer-title-ellipsis a`
* **Product Code**: Parsed from the anchor's `href` attribute value using regex (e.g., `buySubmit\('([^']+)'` matches `26G2066A`).
* **Risk Level Rating**: Inside the card, parsed from inline scripts executing `setFloatMsg("PR2-风险较低")` or by scraping the `风险等级` label.
* **Key Metric Labels (Double Label Component)**:
  * `.ebdp-pc4promote-doublelabel` contains a label span (`.ebdp-pc4promote-doublelabel-text`) and a content div (`.ebdp-pc4promote-doublelabel-content`).
  * *业绩比较基准 (Performance Benchmark)*: Select by text match `业绩比较基准`.
  * *期限 (Product Term)*: Select by text match `期限`.
  * *起购金额 (Minimum Subscription)*: Select by text match `起购金额`.

---

## 4. PDF Prospectus (招募说明书) Integration

Detailed parameters such as management fee rates, custody fee rates, sales service fee rates, specific redemption timelines (T+1 or T+2), FIFO rules, and purchase caps are omitted from all public APIs and HTML pages. Automated systems must download and parse the official product PDF prospectuses.

### 4.1 Discovery Channels
1. **ICBC Official Portal**: Disclosed announcements are posted dynamically in the "理财信息披露" section on `www.icbc.com.cn`. However, links are occasionally buried in subdirectories or require search filters.
2. **ChinaWealth (中国理财网 - www.chinawealth.com.cn)**: As the regulatory depository mandated by the China Banking and Insurance Regulatory Commission, it holds a complete database of prospectuses. Querying by the product's regulatory registration code guarantees access to the PDF.
   * *Example Registration Codes*:
     * `23GS8125` (全球添益双周开): `Z7000823000336`
     * `23GS8689` (天天鑫全球添益): `Z7000823001352`
     * `23GS8123` (月月全球添益): `Z7000823000109` (Queryable via ChinaWealth)

### 4.2 PDF Metadata Contents
Extracting and parsing text from these PDF documents allows population of the following fields:
* **Fixed Management Fee**: Typically `0.15%` per year for the "全球添益" series.
* **Custody Fee**: Typically `0.02%` to `0.03%` per year.
* **Sales Service Fee**: E.g., for `23GS8689`, A-share is `0.30%` per year, B-share is `0.25%` per year.
* **Subscription/Redemption Windows**: Detailed execution guidelines, such as daily open windows for `23GS8689` (天天鑫) versus bi-weekly/monthly open windows for `23GS8125` / `23GS8123`.

---

## 5. Accessibility Classification

| Metadata Characteristic | Accessibility Type | Source | Scrape Effort | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Product Name & Code** | **Easy** | List HTML & Net Value API | Very Low | Directly returned in session-less discovery list and public JSON endpoints. |
| **Risk Level** | **Easy** | List HTML (Scripts) | Very Low | Scraped from `setFloatMsg` or `风险等级` labels. |
| **Establishment & Maturity Dates** | **Medium** | Net Value API (`prodName`) | Low | Statically embedded in the `prodName` field returned by the public API (e.g. `(封闭2023.4.19-2023.10.24)`). |
| **Open / Subscription Windows** | **Medium** | Net Value API & PDF | Low | Indicated by product type and title; specific daily/bi-weekly trading windows and validation times (T+2) require PDF lookup. |
| **Currency** | **Easy** | Net Value API / Name | Very Low | Denominated explicitly in the product name (e.g., "美元产品") or available from the selling currency field. |
| **Management & Custody Fees** | **Only in PDF** | Prospectus PDF | Medium | Omitted in all public HTML and JSON endpoints. Must be scraped from the fee section of the official PDF. |
| **Sales Service Fees** | **Only in PDF** | Prospectus PDF / Announcements | Medium | Varies by share class (A/B/C). Disclosed only in the prospectus or subsequent rate-adjustment announcements. |
| **Detailed Purchase Rules** | **Only in PDF** | Prospectus PDF | Medium | Detailed rules regarding giant redemption thresholds (typically 10%) and redemption queuing are exclusively described in the PDF. |
