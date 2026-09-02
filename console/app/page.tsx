import { fetchPortfolio } from "@/lib/api";
import PortfolioTable from "./PortfolioTable";

export default async function PortfolioPage() {
  const accounts = await fetchPortfolio();

  return (
    <main>
      <h1 className="mb-4 text-xl font-semibold">Portfolio</h1>
      <PortfolioTable accounts={accounts} />
    </main>
  );
}
