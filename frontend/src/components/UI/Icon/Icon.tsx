import {
  Activity,
  ArrowRight,
  Bookmark,
  Category,
  Chat,
  CloseSquare,
  Document,
  Graph,
  Heart,
  Hide,
  Home,
  InfoCircle,
  Paper,
  Search,
  Send,
  Setting,
  Star,
  Swap,
  TickSquare,
  User,
  Wallet,
  Work,
} from "react-iconly";

const glyphs = {
  home: Home,
  account: Wallet,
  payment: Send,
  chart: Graph,
  user: User,
  news: Paper,
  document: Document,
  settings: Setting,
  star: Star,
  search: Search,
  menu: Category,
  switch: Swap,
  arrow: ArrowRight,
  close: CloseSquare,
  bookmark: Bookmark,
  like: Heart,
  hide: Hide,
  spark: Star,
  refresh: Activity,
  building: Work,
  check: TickSquare,
  external: ArrowRight,
  info: InfoCircle,
  chat: Chat,
};

export type IconName = keyof typeof glyphs;

const Icon = ({
  name,
  size = 20,
  color = "currentColor",
  filled = false,
}: { name: IconName; size?: number; color?: string; filled?: boolean }) => {
  const Glyph = glyphs[name];
  return <Glyph size={size} set={filled ? "bold" : "light"} primaryColor={color} />;
};

export default Icon;
