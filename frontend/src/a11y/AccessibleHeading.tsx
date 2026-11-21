import { createContext, useContext, type ReactNode } from "react";

export type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;

const HeadingLevelContext = createContext<HeadingLevel>(1);

export function HeadingLevelProvider({
  level,
  children,
}: {
  level: HeadingLevel;
  children: ReactNode;
}) {
  return (
    <HeadingLevelContext.Provider value={level}>
      {children}
    </HeadingLevelContext.Provider>
  );
}

export interface AccessibleHeadingProps {
  children: ReactNode;
  level?: HeadingLevel;
  id?: string;
}

/** Renders a semantic heading, deriving its depth from context by default. */
export function AccessibleHeading({
  children,
  level,
  id,
}: AccessibleHeadingProps) {
  const contextLevel = useContext(HeadingLevelContext);
  const depth = (level ?? contextLevel + 1) as HeadingLevel;
  const Tag = `h${depth}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
  return <Tag id={id}>{children}</Tag>;
}

export function useHeadingLevel(): HeadingLevel {
  return useContext(HeadingLevelContext);
}
