import { MetricsStrip } from "./MetricsStrip";
import { NetGexSparkline } from "./NetGexSparkline";
import { StatusBadge } from "./StatusBadge";
import { StrikeProfile } from "./StrikeProfile";
import { useCurrentGex } from "@/hooks/useGexQueries";
import { useGexStream } from "@/hooks/useGexStream";
import styles from "./Dashboard.module.scss";

export function Dashboard() {
  // The stream pushes live snapshots into the same query cache the REST
  // bootstrap fills; useCurrentGex then reflects both transparently.
  const { status: wsStatus } = useGexStream();
  const { data: snapshot, isLoading, isError, error } = useCurrentGex();

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <h1 className={styles.heading}>GEX Dashboard</h1>
            {snapshot && (
              <span className={styles.sub}>{snapshot.underlying} · gamma exposure</span>
            )}
          </div>
          {snapshot && (
            <StatusBadge quality={snapshot.quality} wsStatus={wsStatus} />
          )}
        </header>

        {isLoading && !snapshot && (
          <div className={styles.state}>Connecting to feed…</div>
        )}

        {isError && !snapshot && (
          <div className={styles.stateError}>
            Could not reach the backend. Is it running at the configured
            VITE_API_BASE?
            <div className={styles.errorDetail}>
              {error instanceof Error ? error.message : "Unknown error"}
            </div>
          </div>
        )}

        {snapshot && (
          <main className={styles.content}>
            <MetricsStrip snapshot={snapshot} />
            <NetGexSparkline />
            <StrikeProfile
              profile={snapshot.profile}
              spot={snapshot.spot}
              callWall={snapshot.levels.call_wall}
              putWall={snapshot.levels.put_wall}
            />
          </main>
        )}
      </div>
    </div>
  );
}
