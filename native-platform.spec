Name:		native-platform
Version:	0.22.milestone.30
Release:	1
Summary:	Java bindings for native operating system APIs
Group:		Development/Java
License:	ASL 2.0
URL:		https://github.com/gradle/native-platform
# RPM versions and mvn() provides cannot contain a hyphen, so the
# archive name and the POM use dots. sysjar rewrites a request for the
# hyphenated Gradle pin to this version.
%global tag 0.22-milestone-30
%global old_tag 0.22-milestone-26
%global old_ver 0.22.milestone.26
Source0:	https://github.com/gradle/native-platform/archive/refs/tags/%{tag}.tar.gz#/%{name}-%{version}.tar.gz
Source1:	https://github.com/gradle/native-platform/archive/refs/tags/%{old_tag}.tar.gz#/%{name}-%{old_ver}.tar.gz

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
native-platform is the JNI layer Gradle uses for processes, filesystems
and terminals. This package builds that layer from source.
mvn(net.rubygrapefruit:native-platform) is provided at %{version} and at
%{old_ver}. Milestone 30 no longer contains the file-events module, so
mvn(net.rubygrapefruit:file-events) stays at %{old_ver}. The jars contain
the libraries for this architecture, linked against ncurses 6. jsr305 is
compile-only upstream and is stubbed during the build.

%prep
%autosetup -n %{name}-%{tag}
rm -f gradle/wrapper/gradle-wrapper.jar
%setup -q -T -D -a 1 -n %{name}-%{tag}
rm -f %{name}-%{old_tag}/gradle/wrapper/gradle-wrapper.jar
find . \( -name '*.jar' -o -name '*.class' -o -name '*.so' -o -name '*.node' -o -name '*.wasm' \) -delete
chmod a-x readme.md LICENSE %{name}-%{old_tag}/readme.md %{name}-%{old_tag}/LICENSE || :

%build
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH

# com.google.code.findbugs:jsr305 is compileOnly. The packaged jsr305
# modules jar is newer than --release 8, so the three annotations used
# here are stubbed.
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

# root, hyphenated native tag, dotted Maven version, output dir, build file-events
build_one() {
	root="$1"
	tag="$2"
	ver="$3"
	out="$4"
	with_fe="$5"
	mkdir -p "$out/gen/net/rubygrapefruit/platform/internal/jni" "$out/headers" \
		"$out/np-classes" "$out/objs/np" "$out/objs/curses"
	cat > "$out/gen/net/rubygrapefruit/platform/internal/jni/NativeVersion.java" <<END
package net.rubygrapefruit.platform.internal.jni;
public interface NativeVersion {
    String VERSION = "$tag";
}
END
	cat > "$out/headers/native_platform_version.h" <<END
#ifndef __INCLUDE_NATIVE_PLATFORM_VERSION_H__
#define __INCLUDE_NATIVE_PLATFORM_VERSION_H__
#ifdef __cplusplus
extern "C" {
#endif
#define NATIVE_VERSION "$tag"
#ifdef __cplusplus
}
#endif
#endif
END
	find "$root/native-platform/src/main/java" -name '*.java' > "$out/np.sources"
	echo "$out/gen/net/rubygrapefruit/platform/internal/jni/NativeVersion.java" >> "$out/np.sources"
	javac --release 8 -encoding UTF-8 -Xlint:-options \
		-cp jsr305-stub.jar -d "$out/np-classes" -h "$out/headers" @"$out/np.sources"
	jdk_inc="$JAVA_HOME/include"
	cxx="clang++ %{optflags} -std=c++11 -fPIC -D_FILE_OFFSET_BITS=64 -pthread"
	np_inc="-I$out/headers -I$jdk_inc -I$jdk_inc/linux -I$root/native-platform/src/shared/headers"
	i=0
	for src in "$root"/native-platform/src/shared/cpp/*.cpp "$root"/native-platform/src/main/cpp/*.cpp; do
		$cxx $np_inc -c "$src" -o "$(printf "$out/objs/np/%02d.o" "$i")"
		i=$((i + 1))
	done
	clang++ -shared %{build_ldflags} -pthread -o "$out/libnative-platform.so" "$out"/objs/np/*.o
	i=0
	for src in "$root"/native-platform/src/shared/cpp/*.cpp "$root"/native-platform/src/curses/cpp/*.cpp; do
		$cxx $np_inc $(pkg-config --cflags ncursesw) -c "$src" -o "$(printf "$out/objs/curses/%02d.o" "$i")"
		i=$((i + 1))
	done
	clang++ -shared %{build_ldflags} -pthread -o "$out/libnative-platform-curses.so" "$out"/objs/curses/*.o $(pkg-config --libs ncursesw)
	if [ "$with_fe" -eq 1 ]; then
		mkdir -p "$out/fe-classes" "$out/objs/fe"
		cat > "$out/gen/net/rubygrapefruit/platform/internal/jni/FileEventsVersion.java" <<END
package net.rubygrapefruit.platform.internal.jni;
public interface FileEventsVersion {
    String VERSION = "$tag";
}
END
		find "$root/file-events/src/main/java" -name '*.java' > "$out/fe.sources"
		echo "$out/gen/net/rubygrapefruit/platform/internal/jni/FileEventsVersion.java" >> "$out/fe.sources"
		javac --release 8 -encoding UTF-8 -Xlint:-options \
			-cp jsr305-stub.jar:"$out/np-classes" -d "$out/fe-classes" -h "$out/headers" @"$out/fe.sources"
		fe_inc="-I$out/headers -I$jdk_inc -I$jdk_inc/linux -I$root/file-events/src/file-events/headers"
		i=0
		for src in "$root"/file-events/src/file-events/cpp/*.cpp; do
			$cxx $fe_inc -c "$src" -o "$(printf "$out/objs/fe/%02d.o" "$i")"
			i=$((i + 1))
		done
		clang++ -shared %{build_ldflags} -pthread -ldl -o "$out/libnative-platform-file-events.so" "$out"/objs/fe/*.o
	fi
	strip --strip-unneeded "$out"/libnative-platform.so "$out"/libnative-platform-curses.so
	if [ "$with_fe" -eq 1 ]; then
		strip --strip-unneeded "$out"/libnative-platform-file-events.so
	fi
	mkdir -p "$out/np-jar/net/rubygrapefruit/platform/%{np_id}" \
		"$out/np-jar/net/rubygrapefruit/platform/%{np_id}-ncurses6"
	cp -a "$out/np-classes/." "$out/np-jar/"
	rm -rf "$out/np-jar/javax"
	cp "$out/libnative-platform.so" "$out/np-jar/net/rubygrapefruit/platform/%{np_id}/"
	cp "$out/libnative-platform-curses.so" "$out/np-jar/net/rubygrapefruit/platform/%{np_id}-ncurses6/"
	jar cf "$out/native-platform.jar" -C "$out/np-jar" .
	if [ "$with_fe" -eq 1 ]; then
		mkdir -p "$out/fe-jar/net/rubygrapefruit/platform/%{np_id}"
		cp -a "$out/fe-classes/." "$out/fe-jar/"
		rm -rf "$out/fe-jar/javax"
		cp "$out/libnative-platform-file-events.so" "$out/fe-jar/net/rubygrapefruit/platform/%{np_id}/"
		jar cf "$out/file-events.jar" -C "$out/fe-jar" .
	fi
	cat > "$out/native-platform.pom" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>net.rubygrapefruit</groupId>
  <artifactId>native-platform</artifactId>
  <version>$ver</version>
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
EOF
	if [ "$with_fe" -eq 1 ]; then
		cat > "$out/file-events.pom" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>net.rubygrapefruit</groupId>
  <artifactId>file-events</artifactId>
  <version>$ver</version>
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
      <version>$ver</version>
    </dependency>
  </dependencies>
</project>
EOF
	fi
}

build_one . "%{tag}" "%{version}" out30 0
build_one "%{name}-%{old_tag}" "%{old_tag}" "%{old_ver}" out26 1

%install
sysjar install --buildroot %{buildroot} \
	--artifact out26/native-platform.pom:out26/native-platform.jar \
	--file-name rubygrapefruit-platform-%{old_ver} \
	--filelist .mfiles26
# %{version} owns native-platform.sysjar. %{old_ver} keeps a second index.
/bin/mv %{buildroot}/usr/share/sysjar/index/net.rubygrapefruit/native-platform.sysjar \
	%{buildroot}/usr/share/sysjar/index/net.rubygrapefruit/native-platform-%{old_ver}.sysjar
sed -i 's|/usr/share/sysjar/index/net.rubygrapefruit/native-platform\.sysjar|/usr/share/sysjar/index/net.rubygrapefruit/native-platform-%{old_ver}.sysjar|' .mfiles26
sysjar install --buildroot %{buildroot} \
	--artifact out26/file-events.pom:out26/file-events.jar \
	--file-name rubygrapefruit-fileevents \
	--filelist .mfiles-fe
sysjar install --buildroot %{buildroot} \
	--artifact out30/native-platform.pom:out30/native-platform.jar \
	--file-name rubygrapefruit-platform \
	--filelist .mfiles
while IFS= read -r line; do
	grep -qxF -- "$line" .mfiles || printf '%s\n' "$line" >> .mfiles
done < .mfiles26
grep -v '%dir /usr/share/sysjar/index/net.rubygrapefruit' .mfiles-fe > .mfiles-fe-nodir
while IFS= read -r line; do
	grep -qxF -- "$line" .mfiles || printf '%s\n' "$line" >> .mfiles
done < .mfiles-fe-nodir

%check
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH
mkdir -p check
cat > check/Smoke30.java <<'END'
import java.io.File;
import net.rubygrapefruit.platform.Native;
import net.rubygrapefruit.platform.SystemInfo;
import net.rubygrapefruit.platform.terminal.Terminals;

public class Smoke30 {
	public static void main(String[] args) throws Exception {
		File dir = new File(args[1]);
		dir.mkdirs();
		Native n = Native.init(dir);
		SystemInfo info = n.get(SystemInfo.class);
		String kernel = info.getKernelName();
		if (kernel == null || kernel.isEmpty()) {
			throw new AssertionError("empty kernel");
		}
		Terminals terminals = n.get(Terminals.class);
		if (terminals == null) {
			throw new AssertionError("no terminals");
		}
		System.out.println(args[0] + " " + kernel + " " + info.getArchitecture());
	}
}
END
cat > check/Smoke26.java <<'END'
import net.rubygrapefruit.platform.Native;
import net.rubygrapefruit.platform.SystemInfo;
import net.rubygrapefruit.platform.terminal.Terminals;
import net.rubygrapefruit.platform.file.FileEvents;

public class Smoke26 {
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
		System.out.println(args[0] + " " + kernel + " " + info.getArchitecture());
	}
}
END
javac --release 8 -encoding UTF-8 -Xlint:-options \
	-cp out30/native-platform.jar -d check check/Smoke30.java
java --enable-native-access=ALL-UNNAMED \
	-cp check:out30/native-platform.jar Smoke30 np30_ok check/extract30 > check/np30.log
cat check/np30.log
grep -E -q '^np30_ok Linux ' check/np30.log
javac --release 8 -encoding UTF-8 -Xlint:-options \
	-cp out26/native-platform.jar:out26/file-events.jar -d check check/Smoke26.java
java --enable-native-access=ALL-UNNAMED \
	-cp check:out26/native-platform.jar:out26/file-events.jar Smoke26 np26_ok > check/np26.log
cat check/np26.log
grep -E -q '^np26_ok Linux ' check/np26.log

%files -f .mfiles
%doc LICENSE readme.md
