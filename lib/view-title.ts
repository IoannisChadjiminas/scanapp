export function viewTitle(card: { name: string; view_title?: string | null }): string {
  const title = card.view_title?.trim();
  return title || card.name;
}
