Name:		native-platform
Version:	0.22.milestone.26
Release:	1
Summary:	Java bindings for native operating system APIs
Group:		Development/Java
License:	ASL 2.0
URL:		https://github.com/gradle/native-platform
# Gradle 8.11.1 strictly requests 0.22-milestone-26. RPM versions and
# mvn() provides cannot contain a hyphen, so the archive and the POM use
# dots. sysjar rewrites a request for the hyphenated version to this one.
%global tag 0.22-milestone-26
Source0:	https://github.com/gradle/native-platform/archive/refs/tags/%{tag}.tar.gz#/%{name}-%{version}.tar.gz

%ifarch aarch64
%global np_id linux-aarch64
%endif
%ifarch x86_64 znver1
%global np_id linux-amd64
%endif
%{!?np_id:%{error:No native-platform library id for %{_arch}}}

BuildRequires:	java-current-devel
BuildRequires:	sysjar
BuildRequires:	clang
BuildRequires:	libstdc++-devel
BuildRequires:	pkgconfig(ncursesw)
BuildRequires:	binutils
# The JNI libraries live inside the jars, so there is no ELF debuginfo.
%global debug_package %{nil}
# The JNI libraries are extracted from the jars and loaded with System.load.
# rpm does not see those ELF files, so the sonames are explicit.
Requires:	libncursesw.so.6()(64bit)
Requires:	libstdc++.so.6()(64bit)

%description
native-platform is the JNI layer Gradle uses for processes, filesystems,
terminals and inotify file watching. This package builds that layer from
source and provides mvn(net.rubygrapefruit:native-platform) and
mvn(net.rubygrapefruit:file-events) at %{version}. Gradle 8.11.1 asks for
%{tag}, and sysjar rewrites that request. The jars contain the libraries
for this architecture, linked against ncurses 6. jsr305 is compile-only
upstream and is stubbed during the build.

%prep
%autosetup -n %{name}-%{tag}
rm -f gradle/wrapper/gradle-wrapper.jar
chmod a-x readme.md LICENSE || :

%build
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH

# com.google.code.findbugs:jsr305 is compileOnly and is not in cooker.
mkdir -p stub/javax/annotation/concurrent
cat > stub/javax/annotation/Nullable.java <<'END'
package javax.annotation;
import java.lang.annotation.*;
@Retention(RetentionPolicy.CLASS)
@Target({ElementType.METHOD, ElementType.FIELD, ElementType.PARAMETER, ElementType.LOCAL_VARIABLE, ElementType.TYPE_USE, ElementType.TYPE})
public @interface Nullable {}
END
cat > stub/javax/annotation/CheckReturnValue.java <<'END'
package javax.annotation;
import java.lang.annotation.*;
@Retention(RetentionPolicy.CLASS)
@Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
public @interface CheckReturnValue {}
END
cat > stub/javax/annotation/concurrent/NotThreadSafe.java <<'END'
package javax.annotation.concurrent;
import java.lang.annotation.*;
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface NotThreadSafe {}
END
javac --release 8 -encoding UTF-8 -Xlint:-options -d stub \
	stub/javax/annotation/Nullable.java \
	stub/javax/annotation/CheckReturnValue.java \
	stub/javax/annotation/concurrent/NotThreadSafe.java
jar cf jsr305-stub.jar -C stub javax

# The same string is compiled into the Java interface and the native
# header. Native.init rejects a library whose version does not match.
mkdir -p gen/net/rubygrapefruit/platform/internal/jni headers
cat > gen/net/rubygrapefruit/platform/internal/jni/NativeVersion.java <<END
package net.rubygrapefruit.platform.internal.jni;
public interface NativeVersion {
    String VERSION = "%{tag}";
}
END
cat > gen/net/rubygrapefruit/platform/internal/jni/FileEventsVersion.java <<END
package net.rubygrapefruit.platform.internal.jni;
public interface FileEventsVersion {
    String VERSION = "%{tag}";
}
END
cat > headers/native_platform_version.h <<END
#ifndef __INCLUDE_NATIVE_PLATFORM_VERSION_H__
#define __INCLUDE_NATIVE_PLATFORM_VERSION_H__
#ifdef __cplusplus
extern "C" {
#endif
#define NATIVE_VERSION "%{tag}"
#ifdef __cplusplus
}
#endif
#endif
END

mkdir -p np-classes fe-classes
find native-platform/src/main/java -name '*.java' > np.sources
echo gen/net/rubygrapefruit/platform/internal/jni/NativeVersion.java >> np.sources
javac --release 8 -encoding UTF-8 -Xlint:-options \
	-cp jsr305-stub.jar -d np-classes -h headers @np.sources
find file-events/src/main/java -name '*.java' > fe.sources
echo gen/net/rubygrapefruit/platform/internal/jni/FileEventsVersion.java >> fe.sources
javac --release 8 -encoding UTF-8 -Xlint:-options \
	-cp jsr305-stub.jar:np-classes -d fe-classes -h headers @fe.sources

jdk_inc="$JAVA_HOME/include"
cxx="clang++ %{optflags} -std=c++11 -fPIC -D_FILE_OFFSET_BITS=64 -pthread"
np_inc="-Iheaders -I$jdk_inc -I$jdk_inc/linux -Inative-platform/src/shared/headers"
fe_inc="-Iheaders -I$jdk_inc -I$jdk_inc/linux -Ifile-events/src/file-events/headers"
# glibc marks readdir_r deprecated. Upstream passes -Werror, which fails here.
mkdir -p objs/np objs/curses objs/fe
i=0
for src in native-platform/src/shared/cpp/*.cpp native-platform/src/main/cpp/*.cpp; do
	$cxx $np_inc -c "$src" -o "$(printf 'objs/np/%02d.o' "$i")"
	i=$((i + 1))
done
clang++ -shared %{build_ldflags} -pthread -o libnative-platform.so objs/np/*.o

i=0
for src in native-platform/src/shared/cpp/*.cpp native-platform/src/curses/cpp/*.cpp; do
	$cxx $np_inc $(pkg-config --cflags ncursesw) -c "$src" -o "$(printf 'objs/curses/%02d.o' "$i")"
	i=$((i + 1))
done
clang++ -shared %{build_ldflags} -pthread -o libnative-platform-curses.so objs/curses/*.o $(pkg-config --libs ncursesw)

i=0
for src in file-events/src/file-events/cpp/*.cpp; do
	$cxx $fe_inc -c "$src" -o "$(printf 'objs/fe/%02d.o' "$i")"
	i=$((i + 1))
done
clang++ -shared %{build_ldflags} -pthread -ldl -o libnative-platform-file-events.so objs/fe/*.o

strip --strip-unneeded libnative-platform.so libnative-platform-curses.so libnative-platform-file-events.so

mkdir -p np-jar/net/rubygrapefruit/platform/%{np_id} \
	np-jar/net/rubygrapefruit/platform/%{np_id}-ncurses6 \
	fe-jar/net/rubygrapefruit/platform/%{np_id}
cp -a np-classes/. np-jar/
cp -a fe-classes/. fe-jar/
rm -rf np-jar/javax fe-jar/javax
cp libnative-platform.so np-jar/net/rubygrapefruit/platform/%{np_id}/
cp libnative-platform-curses.so np-jar/net/rubygrapefruit/platform/%{np_id}-ncurses6/
cp libnative-platform-file-events.so fe-jar/net/rubygrapefruit/platform/%{np_id}/
jar cf native-platform.jar -C np-jar .
jar cf file-events.jar -C fe-jar .

cat > native-platform.pom <<END
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>net.rubygrapefruit</groupId>
  <artifactId>native-platform</artifactId>
  <version>%{version}</version>
  <name>native-platform</name>
  <description>Java bindings for native operating system APIs.</description>
  <url>https://github.com/gradle/native-platform</url>
  <licenses>
    <license>
      <name>Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
  </licenses>
</project>
END
cat > file-events.pom <<END
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>net.rubygrapefruit</groupId>
  <artifactId>file-events</artifactId>
  <version>%{version}</version>
  <name>file-events</name>
  <description>Native file-system watching for Gradle.</description>
  <url>https://github.com/gradle/native-platform</url>
  <licenses>
    <license>
      <name>Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
  </licenses>
  <dependencies>
    <dependency>
      <groupId>net.rubygrapefruit</groupId>
      <artifactId>native-platform</artifactId>
      <version>%{version}</version>
    </dependency>
  </dependencies>
</project>
END

%check
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH
mkdir -p check
cat > check/Smoke.java <<'END'
import net.rubygrapefruit.platform.Native;
import net.rubygrapefruit.platform.SystemInfo;
import net.rubygrapefruit.platform.terminal.Terminals;
import net.rubygrapefruit.platform.file.FileEvents;

public class Smoke {
	public static void main(String[] args) {
		SystemInfo info = Native.get(SystemInfo.class);
		String kernel = info.getKernelName();
		if (kernel == null || kernel.isEmpty()) {
			throw new AssertionError("empty kernel");
		}
		Terminals terminals = Native.get(Terminals.class);
		if (terminals == null) {
			throw new AssertionError("no terminals");
		}
		FileEvents.init(null);
		System.out.println(kernel + " " + info.getArchitecture());
	}
}
END
javac --release 8 -encoding UTF-8 -Xlint:-options \
	-cp native-platform.jar:file-events.jar -d check check/Smoke.java
java -cp check:native-platform.jar:file-events.jar Smoke

%install
# "native" is a Java keyword, so native-platform.jar cannot be an automatic
# module and jmod.deps would provide jmod(Unable). These file names derive
# rubygrapefruit.platform and rubygrapefruit.fileevents.
sysjar install --buildroot %{buildroot} \
	--artifact native-platform.pom:native-platform.jar \
	--file-name rubygrapefruit-platform \
	--filelist .mfiles
sysjar install --buildroot %{buildroot} \
	--artifact file-events.pom:file-events.jar \
	--file-name rubygrapefruit-fileevents \
	--filelist .mfiles-fe
grep -v '%dir /usr/share/sysjar/index/net.rubygrapefruit' .mfiles-fe >> .mfiles

%files -f .mfiles
%doc LICENSE readme.md
