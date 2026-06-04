# Bank of China (BOC) & BOC Wealth Management (BOCWM) Data Investigation Report

This report outlines the technical findings regarding the structure, location, and accessibility of wealth management product characteristics (currency, dates, fees, open/closed windows, sales regions) on the BOC and BOCWM websites.

---

## 1. API Metadata Discovery

BOC Wealth Management (`www.bocwm.cn`) uses a RESTful JSON API back-end. Most product-related queries are performed via HTTP requests. Below are the key endpoints and their metadata availability.

### 1.1 Product List API
* **Endpoint URL**: `POST https://www.bocwm.cn/webApi/cms/product/queryStaticProducts`
* **Request Format (JSON)**:
  ```json
  {
    "pageNo": 1,
    "pageSize": 20
  }
  ```
* **Sample Response (JSON)**:
  ```json
  {
    "result": true,
    "data": {
      "total": 456,
      "rows": [
        {
          "productCode": "WFBYZQBO2627",
          "productName": "中银理财-稳富博弈固收增强二元策略封闭式2026年第27期",
          "startsPrice": 1.0,
          "riskLevel": "R2中低风险",
          "productDetailUrl": "/3/9634.html",
          "shareNetWorth": "1.000000",
          "cumulativeNetWorth": "1.000000",
          "releaseDate": "2026-06-02",
          "pageNo": 0,
          "pageSize": 0
        }
      ]
    }
  }
  ```
* **Retrieved Metadata**: `productCode`, `productName`, `startsPrice` (minimum purchase amount), `riskLevel`, `productDetailUrl` (points to the static details page ID), `releaseDate` (establishment date, optional).
* **Missing Metadata**: Currency, maturity date, fees, open/closed subscription windows, and sales regions are **not** present in the list response.

### 1.2 Detail Page APIs
To populate the details page of a product, several secondary GET APIs are invoked asynchronously by the client side (Vue.js) using the product code:

1. **Historical Net Values (Chart)**:
   * **Endpoint**: `GET https://www.bocwm.cn/webApi/cms/productNetWorth/getNetWorthImageByCode`
   * **Parameters**: `productCode` (string), `dayCount` (string, optional e.g. `"30"`, `"90"`, `"180"`, `"365"`)
   * **Response**: Returns history lists: `dateList`, `shareNetWorthList` (unit net worth), `cumulativeNetWorthList` (cumulative net worth), `sevenDayAnnualizationList` (for cash management), and `eachTenThousandProfitList`.
2. **Net Worth Table (List)**:
   * **Endpoint**: `GET https://www.bocwm.cn/webApi/cms/productNetWorth/getNetWorthByCode`
   * **Parameters**: `productCode` (string), `pageNo` (int), `pageSize` (int)
   * **Response**: Tabular net worth records and `productType` (e.g. `"封闭"`, `"定期开放"`, `"现金管理"`).
3. **Next Open Date**:
   * **Endpoint**: `GET https://www.bocwm.cn/webApi/cms/productOpenDate/getOpenDate`
   * **Parameters**: `productCode` (string)
   * **Response**: The next open date as a string (e.g. `"2026-09-02"` or `"-"` for closed products).
4. **Product Prospectus List (Instructions)**:
   * **Endpoint**: `GET https://www.bocwm.cn/webApi/cms/productDynamicPage/getProductInstructionsList`
   * **Parameters**: `productCode` (string)
   * **Response**: A list containing links to the PDF prospectus, risk disclosure, and investor agreement documents.
     ```json
     {
       "result": true,
       "data": [
         {
           "title": "中银理财-稳富博弈固收增强二元策略封闭式2026年第27期产品说明书-WFBYZQBO2627",
           "contentPath": "/upload/1/cms/content/17799302875373727.pdf",
           "contentDatetime": "2026-06-02 10:00:00"
         }
       ]
     }
     ```

---

## 2. HTML Detail Page Structure

The product detail pages on `www.bocwm.cn` are Vue.js containers (e.g. `/html/1/3/{ID}.html`). Key data parameters are generated on the server and written statically into the Vue `created` hook or inside HTML tags:

### 2.1 HTML Selector Paths
* **Product Name**: `.row-title`
  * *Selector*: `div.row-title`
* **Product Code & Registration Code**: `.row-ts`
  * *Selector*: `div.row-ts`
  * *Format*: `产品代码: WFBYZQBO2627 | 理财登记编码: Z7001026000713`
* **Risk Level**: Inside `.toprow` where label spans `风险等级:`
  * *Selector*: `div.toprow:has(span:contains("风险等级"))`
* **Starting Purchase Amount & Currency**: Inside `.toprow` where label spans `起购金额:`
  * *Selector*: `div.toprow:has(span:contains("起购金额"))`
  * *Format*: `1.00人民币元` or `1,000.00美元` (Currency unit is explicitly present in the text)
* **Subscription Period**: Inside `.toprow` where label spans `认购期:`
  * *Selector*: `div.toprow:has(span:contains("认购期"))`
  * *Format*: `2026-06-02~2026-06-08`
* **Establishment/Release Date**: Inside `.toprow` where label spans `成立日:`
  * *Selector*: `div.toprow:has(span:contains("成立日"))` (also declared in script: `let clr = '2026-06-09'`)
* **Maturity Date (Closed Products)**: Inside `.toprow` where label spans `到期日:`
  * *Selector*: `div.toprow:has(span:contains("到期日"))`
* **Product Term/Duration**: Inside `.toprow` where label spans `产品存续期限:`
  * *Selector*: `div.toprow:has(span:contains("产品存续期限"))` (often declared in script: `termkt: '339天'`)
* **Shortest Holding Period**: Inside `.toprow` where label spans `最短持有期:`
  * *Selector*: `div.toprow:has(span:contains("最短持有期"))` (often declared in script: `shrtstHoldTerm: '180天'`)

### 2.2 Dynamic Properties
The detail HTML page references Vue properties populated by dynamic endpoints:
* **Next Open Date**: `{{openDate}}` (fetched from `/webApi/cms/productOpenDate/getOpenDate`)
* **Performance Benchmark**: If `isXinPin = true`, the benchmark text is shown. In many cases, it points to the PDF prospectus with a static placeholder text.

---

## 3. PDF Prospectus (招股说明书) Integration

Because individual detail pages and public REST APIs omit detailed fee rates, redemption/subscription schedules, and sales restrictions, downloading and parsing the PDF prospectuses is mandatory for complete characteristic extraction.

### 3.1 PDF Listing Locations
PDF prospectuses are published on two primary listing channels:
1. **BOC Corporate Disclosure**: `https://www.boc.cn/fimarkets/bocwm/fp83/index.html` (paginated as `index.html`, `index_1.html`, etc.)
2. **BOCWM Official Portal**: `https://www.bocwm.cn/html/1/198/200/index.html` (paginated as `index.html`, `list-2.html`, etc.)

### 3.2 Naming & Matching Convention
* **URL Formats**:
  * BOC: `https://pic.bankofchina.com/bocappd/wealth/cs81/YYYYMM/Pxxxxxxxxx.pdf`
  * BOCWM: `https://www.bocwm.cn/upload/1/cms/content/xxxxxxxxx.pdf`
* **Matching**: Filenames are arbitrary hashes or sequence IDs. However, the anchor link title (text) contains the product code as a suffix:
  * *Example link text*: `中银理财-智富创新驱动180天持有期固收增强理财产品产品说明书-CYQZFCXQD180D`
  * *Regex matching*: `.*产品说明书-(?P<code>[A-Z0-9]+)$` maps the PDF directly to the target product code (`CYQZFCXQD180D`).

### 3.3 Text Extraction Feasibility
Tests using standard Python libraries (like `pypdf`) confirm that text extraction is highly reliable. Chinese character mappings are intact (valid Unicode code points), and tables can be parsed line-by-line.

Key sections inside the PDF prospectus containing the missing characteristics:
* **Currency**: `理财本金/理财本金返还/理财收益币种` (e.g. 人民币, 美元)
* **Sales Regions / Targets**: `产品销售机构` or `销售对象/销售区域` (e.g. 面向中国银行个人与机构客户)
* **Detailed Dates**: `认购期` (Start/End dates), `成立日`, `存续期限`
* **Fees (Fixed & Performance)**:
  * `固定管理费`: e.g. `0.30%` (年化)
  * `销售服务费`: e.g. `0.45%` (年化)
  * `托管费`: e.g. `0.025%` (年化)
  * `超额业绩报酬`: e.g. `暂不收取超额业绩报酬` or excess return splits.
* **Subscription & Redemption Windows**:
  * Minimum holding periods (e.g., `180个自然日`)
  * Business day confirmation schedules (`T+2` day confirmation)
  * Redemption queue order (e.g. `先进先出` / FIFO)
  * Giant redemption caps (`巨额赎回限制`, e.g. `10%` threshold)

---

## 4. Accessibility Classification

| Metadata Characteristic | Accessibility Type | Source | Scrape Effort | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Product Name & Code** | **Easy** | REST API & Detail HTML | Very Low | Directly accessible in list API. |
| **Risk Level** | **Easy** | REST API & Detail HTML | Very Low | `riskLevel` field returned in list API. |
| **Currency** | **Medium** | Detail HTML & PDF | Low | Can be extracted from start price string in HTML (e.g., "1.00人民币元") or explicitly from PDF. |
| **Release / Establishment Date**| **Medium** | Detail HTML & REST API | Low | Statically written in HTML Vue config (e.g. `clr = '2026-06-09'`) or returned via API. |
| **Maturity Date** | **Medium** | Detail HTML | Low | For closed-end products, it is rendered in HTML selectors (e.g. `到期日: 2027-05-14`). |
| **Open / Subscription Windows** | **Medium** | Detail HTML & REST API | Low | Next open date returned dynamically via `/getOpenDate` endpoint. Detailed rules (T+2, FIFO) require PDF. |
| **Sales Regions / Channels** | **Only in PDF** | Prospectus PDF | Medium | Omitted in all HTML / API responses. Must be extracted from `销售机构/销售对象` section of PDF. |
| **Management & Custody Fees** | **Only in PDF** | Prospectus PDF | Medium | Omitted in HTML / API responses. Must parse the `理财产品费用` section in the PDF. |
| **Performance Benchmark & Fees**| **Only in PDF** | Prospectus PDF | Medium | HTML only states "see prospectus". Complex formula and excess return splits are explicitly described only in the PDF. |
