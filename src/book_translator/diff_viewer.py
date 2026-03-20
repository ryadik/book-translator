"""
Interactive diff viewer for proofreading review.

Allows users to review each LLM-generated diff before it is applied,
accepting or rejecting changes individually.
"""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


def show_proofreading_diffs(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interactively review proofreading diffs, returning only accepted ones.

    Each diff is displayed with the original and replacement text.
    The user can accept (a), reject (r), accept all remaining (A), or quit (q).

    Args:
        diffs: List of diff dicts with keys: chunk_index, find, replace.

    Returns:
        List of accepted diffs (subset of input).
    """
    if not diffs:
        return []

    accepted = []
    total = len(diffs)

    console.print(f"\n[bold cyan]📝 Просмотр правок вычитки[/bold cyan] — {total} правок\n")
    console.print("[dim]Команды: [green]a[/green]=принять, [red]r[/red]=отклонить, [green]A[/green]=принять все, [red]q[/red]=выйти[/dim]\n")

    for i, diff in enumerate(diffs, 1):
        chunk_idx = diff.get('chunk_index', '?')
        find_str = str(diff.get('find', ''))
        replace_str = str(diff.get('replace', ''))

        # Build display panel
        original_text = Text(find_str, style="red")
        replacement_text = Text(replace_str, style="green")

        console.print(Panel(
            f"[bold]Было:[/bold]\n{original_text}\n\n[bold]Стало:[/bold]\n{replacement_text}",
            title=f"[cyan]Правка {i}/{total}[/cyan] · чанк #{chunk_idx}",
            box=box.ROUNDED,
            border_style="cyan",
        ))

        while True:
            try:
                choice = console.input("[bold]→[/bold] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Просмотр прерван. Применены только принятые правки.[/yellow]")
                return accepted

            if choice == 'a':
                accepted.append(diff)
                console.print("[green]✔ Принято[/green]")
                break
            elif choice == 'r':
                console.print("[red]✘ Отклонено[/red]")
                break
            elif choice == 'a' or choice.upper() == 'A':
                # Accept all remaining
                accepted.append(diff)
                accepted.extend(diffs[i:])  # i is 1-based, diffs[i:] skips current
                console.print(f"[green]✔ Принято всё остальное ({total - i + 1} правок)[/green]")
                return accepted
            elif choice == 'q':
                console.print("[yellow]Просмотр завершён досрочно.[/yellow]")
                return accepted
            else:
                console.print("[dim]Неверная команда. Введите a, r, A или q.[/dim]")

    console.print(f"\n[bold green]✅ Итог: принято {len(accepted)}/{total} правок[/bold green]")
    return accepted
