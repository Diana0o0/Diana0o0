"""高级财务助手：从票据文本提取并汇总关键信息。

核心行为：
- 识别单据数量（按空行或自定义分隔符拆分）。
- 从单据提取日期、城市、简述、金额、货币，缺失字段标注为"缺失"。
- 生成 `日期 | 城市 | 简述 | 金额 | 货币` 的 Markdown 表格并保留金额两位小数。
- 支持多次输入的连续汇总，并按需要排序或维持输入顺序。
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DATE_PATTERNS: Sequence[str] = (
    r"\d{4}-\d{1,2}-\d{1,2}",  # 2024-05-10
    r"\d{4}/\d{1,2}/\d{1,2}",  # 2024/05/10
    r"\d{4}年\d{1,2}月\d{1,2}日?",  # 2024年5月10日
    r"\d{1,2}-\d{1,2}-\d{4}",  # 10-05-2024
    r"\d{1,2}/\d{1,2}/\d{4}",  # 10/05/2024
)

CURRENCY_MAP: Dict[str, str] = {
    "￥": "CNY",
    "¥": "CNY",
    "RMB": "CNY",
    "CNY": "CNY",
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "EUR": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "£": "GBP",
    "HKD": "HKD",
    "JPY": "JPY",
    "日元": "JPY",
}

AMOUNT_PATTERN = re.compile(
    r"(?P<currency>[A-Z]{3}|USD|EUR|GBP|HKD|CNY|RMB|JPY|US\$|\$|€|£|￥|¥)?\s*"
    r"(?P<amount>-?\d+(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)

CITY_KEYS = ("城市", "地点", "开票地", "city")
DESCRIPTION_KEYS = ("简述", "描述", "摘要", "事项", "备注", "项目", "事由", "说明")


@dataclass
class InvoiceEntry:
    date: str
    city: str
    description: str
    amount: Optional[float]
    currency: str

    def formatted_amount(self) -> str:
        if self.amount is None:
            return "缺失"
        return f"{self.amount:.2f}"

    def as_markdown_row(self) -> str:
        return " | ".join(
            [self.date or "缺失", self.city or "缺失", self.description or "缺失", self.formatted_amount(), self.currency or "缺失"]
        )

    @staticmethod
    def from_dict(data: Dict[str, object]) -> "InvoiceEntry":
        amount = data.get("amount")
        amount_value = float(amount) if isinstance(amount, (int, float, str)) and str(amount) not in {"", "缺失"} else None
        return InvoiceEntry(
            date=str(data.get("date", "缺失")),
            city=str(data.get("city", "缺失")),
            description=str(data.get("description", "缺失")),
            amount=amount_value,
            currency=str(data.get("currency", "缺失")),
        )


class InvoiceExtractor:
    def __init__(self, delimiter: Optional[str] = None) -> None:
        self.delimiter = delimiter or "---"

    def split_documents(self, text: str) -> List[str]:
        if not text.strip():
            return []
        if self.delimiter in text:
            parts = re.split(rf"{re.escape(self.delimiter)}", text)
        else:
            parts = re.split(r"\n\s*\n", text)
        return [part.strip() for part in parts if part.strip()]

    def extract(self, text: str) -> List[InvoiceEntry]:
        documents = self.split_documents(text)
        return [self._extract_single(doc) for doc in documents]

    def _extract_single(self, document: str) -> InvoiceEntry:
        date = self._extract_date(document)
        city = self._extract_field(document, CITY_KEYS)
        amount, currency = self._extract_amount_and_currency(document)
        description = self._extract_description(document, known_date=date, known_city=city, known_amount=amount)
        return InvoiceEntry(
            date=date or "缺失",
            city=city or "缺失",
            description=description or "缺失",
            amount=amount,
            currency=currency or "缺失",
        )

    def _extract_date(self, text: str) -> str:
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                raw_date = match.group(0)
                normalized = self._normalize_date(raw_date)
                return normalized or raw_date
        return ""

    def _normalize_date(self, date_str: str) -> Optional[str]:
        cleaned = date_str.replace("年", "-").replace("月", "-").replace("日", "")
        cleaned = cleaned.replace("/", "-")
        cleaned = re.sub(r"-+", "-", cleaned)
        candidates = [
            ("%Y-%m-%d", cleaned),
            ("%d-%m-%Y", cleaned),
            ("%Y-%m", cleaned),
        ]
        for fmt, value in candidates:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _extract_field(self, text: str, keys: Sequence[str]) -> str:
        for key in keys:
            pattern = rf"{key}[:：]?\s*([\u4e00-\u9fa5A-Za-z·\s]+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_amount_and_currency(self, text: str) -> Tuple[Optional[float], str]:
        match = AMOUNT_PATTERN.search(text)
        if not match:
            return None, ""
        raw_currency = (match.group("currency") or "").upper()
        currency = CURRENCY_MAP.get(raw_currency, CURRENCY_MAP.get(raw_currency.upper(), raw_currency)) if raw_currency else ""
        amount_str = match.group("amount").replace(",", ".")
        try:
            amount_value = float(amount_str)
        except ValueError:
            return None, currency or ""
        return amount_value, currency or ""

    def _extract_description(self, text: str, known_date: str, known_city: str, known_amount: Optional[float]) -> str:
        for key in DESCRIPTION_KEYS:
            pattern = rf"{key}[:：]?\s*(.+)"
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        filtered: List[str] = []
        for line in lines:
            if known_date and known_date in line:
                continue
            if known_city and known_city in line:
                continue
            if re.search(AMOUNT_PATTERN, line):
                continue
            filtered.append(line)
        return filtered[0] if filtered else ""


class InvoiceAggregator:
    def __init__(self) -> None:
        self.entries: List[InvoiceEntry] = []

    def add_entries(self, new_entries: Iterable[InvoiceEntry]) -> None:
        self.entries.extend(new_entries)

    def as_markdown(self, order: str = "input") -> str:
        ordered = self._ordered_entries(order)
        lines = ["| 日期 | 城市 | 简述 | 金额 | 货币 |", "| --- | --- | --- | --- | --- |"]
        lines.extend([f"| {entry.as_markdown_row()} |" for entry in ordered])
        return "\n".join(lines)

    def totals_by_currency(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for entry in self.entries:
            if entry.amount is None or not entry.currency:
                continue
            totals[entry.currency] = totals.get(entry.currency, 0.0) + entry.amount
        return totals

    def _ordered_entries(self, order: str) -> List[InvoiceEntry]:
        if order != "date":
            return list(self.entries)
        dated = []
        undated = []
        for idx, entry in enumerate(self.entries):
            parsed = self._parse_date(entry.date)
            if parsed:
                dated.append((parsed, idx, entry))
            else:
                undated.append((idx, entry))
        dated.sort(key=lambda item: (item[0], item[1]))
        ordered = [item[2] for item in dated]
        ordered.extend(entry for _, entry in undated)
        return ordered

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def to_state(self) -> List[Dict[str, object]]:
        return [asdict(entry) for entry in self.entries]

    @staticmethod
    def from_state(state: List[Dict[str, object]]) -> "InvoiceAggregator":
        agg = InvoiceAggregator()
        agg.entries = [InvoiceEntry.from_dict(item) for item in state]
        return agg


def load_state(path: Optional[Path]) -> InvoiceAggregator:
    if path and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return InvoiceAggregator.from_state(data)
    return InvoiceAggregator()


def save_state(path: Optional[Path], aggregator: InvoiceAggregator) -> None:
    if not path:
        return
    path.write_text(json.dumps(aggregator.to_state(), ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从票据文本提取并汇总关键信息")
    parser.add_argument("--files", nargs="*", help="要处理的文本文件路径，按传入顺序解析")
    parser.add_argument("--text", help="直接传入包含单据的文本内容")
    parser.add_argument("--delimiter", default="---", help="单据分隔符，默认'---'，若不存在则按空行拆分")
    parser.add_argument("--state", type=Path, help="状态文件路径；若存在则先加载历史记录")
    parser.add_argument("--order", choices=["input", "date"], default="input", help="汇总表顺序，input按输入顺序，date按日期排序")
    return parser.parse_args(argv)


def read_inputs(file_paths: Sequence[str]) -> List[str]:
    contents: List[str] = []
    for path_str in file_paths:
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"未找到文件：{path}")
        contents.append(path.read_text(encoding="utf-8"))
    return contents


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    extractor = InvoiceExtractor(delimiter=args.delimiter)
    aggregator = load_state(args.state)

    file_texts = read_inputs(args.files or []) if args.files else []
    texts = file_texts + ([args.text] if args.text else [])
    for text in texts:
        entries = extractor.extract(text)
        aggregator.add_entries(entries)

    markdown_table = aggregator.as_markdown(order=args.order)
    print(markdown_table)

    totals = aggregator.totals_by_currency()
    if totals:
        print("\n按货币汇总：")
        for currency, amount in totals.items():
            print(f"- {currency}: {amount:.2f}")
    else:
        print("\n按货币汇总：暂无可汇总的金额")

    save_state(args.state, aggregator)


if __name__ == "__main__":
    main()

